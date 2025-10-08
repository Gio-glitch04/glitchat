using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace ClientC
{
    internal sealed class ChatClientForm : Form
    {
        private const string DefaultHost = "127.0.0.1";
        private const int DefaultPort = 55555;
        private const int LoadChunk = 100;

        private readonly TextBox _serverEntry;
        private readonly TextBox _portEntry;
        private readonly TextBox _userEntry;
        private readonly Button _connectButton;
        private readonly Button _saveServerButton;
        private readonly ComboBox _serversCombo;
        private readonly ListBox _roomsListBox;
        private readonly Label _sidebarTitle;
        private readonly Button _showJoinedButton;
        private readonly Button _listPublicButton;
        private readonly Button _createJoinButton;
        private readonly Label _activeRoomLabel;
        private readonly ChatRichTextBox _chatArea;
        private readonly TextBox _messageEntry;
        private readonly Button _sendButton;
        private readonly ContextMenuStrip _roomsMenu;

        private readonly ServerStore _serverStore = new ServerStore();

        private TcpClient _client;
        private StreamReader _reader;
        private StreamWriter _writer;
        private Thread _listenerThread;
        private volatile bool _running;
        private string _username = string.Empty;
        private string _serverKey = "default";
        private string _currentRoom = "global";
        private SidebarMode _sidebarMode = SidebarMode.Joined;
        private readonly HashSet<string> _visitedRooms = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "global" };
        private readonly Dictionary<string, RoomHistoryState> _historyIndex = new Dictionary<string, RoomHistoryState>(StringComparer.OrdinalIgnoreCase);
        private readonly List<RoomListEntry> _publicRoomsCache = new List<RoomListEntry>();
        private readonly Dictionary<string, string> _roomPasswords = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private string _pendingJoinRoom;
        private string _pendingJoinPassword;

        private readonly object _sendLock = new object();

        public ChatClientForm()
        {
            Text = "Chat - Cliente (Windows Forms)";
            Width = 980;
            Height = 560;

            FlowLayoutPanel topPanel = new FlowLayoutPanel
            {
                Dock = DockStyle.Top,
                AutoSize = true,
                Padding = new Padding(8, 6, 8, 6)
            };

            topPanel.Controls.Add(new Label { Text = "Servidor:", AutoSize = true, TextAlign = System.Drawing.ContentAlignment.MiddleLeft });
            _serverEntry = new TextBox { Width = 120, Text = DefaultHost };
            topPanel.Controls.Add(_serverEntry);

            topPanel.Controls.Add(new Label { Text = "Puerto:", AutoSize = true, Margin = new Padding(8, 0, 0, 0) });
            _portEntry = new TextBox { Width = 60, Text = DefaultPort.ToString() };
            topPanel.Controls.Add(_portEntry);

            topPanel.Controls.Add(new Label { Text = "Usuario:", AutoSize = true, Margin = new Padding(8, 0, 0, 0) });
            _userEntry = new TextBox { Width = 120 };
            topPanel.Controls.Add(_userEntry);

            _connectButton = new Button { Text = "Conectar", Margin = new Padding(8, 0, 0, 0) };
            _connectButton.Click += delegate { Connect(); };
            topPanel.Controls.Add(_connectButton);

            topPanel.Controls.Add(new Label { Text = "Recientes:", AutoSize = true, Margin = new Padding(12, 0, 0, 0) });
            _serversCombo = new ComboBox { Width = 150, DropDownStyle = ComboBoxStyle.DropDownList };
            _serversCombo.SelectedIndexChanged += delegate { OnServerSelected(); };
            topPanel.Controls.Add(_serversCombo);

            _saveServerButton = new Button { Text = "Guardar servidor...", Margin = new Padding(8, 0, 0, 0) };
            _saveServerButton.Click += delegate { SaveCurrentServer(); };
            topPanel.Controls.Add(_saveServerButton);

            Controls.Add(topPanel);

            Panel mainPanel = new Panel { Dock = DockStyle.Fill, Padding = new Padding(8, 0, 8, 6) };
            Controls.Add(mainPanel);

            Panel sidebarPanel = new Panel { Dock = DockStyle.Left, Width = 240, Padding = new Padding(0, 0, 8, 0) };
            mainPanel.Controls.Add(sidebarPanel);

            _sidebarTitle = new Label { Text = "Salas (doble clic para activar)", Dock = DockStyle.Top, AutoSize = true };
            sidebarPanel.Controls.Add(_sidebarTitle);

            _roomsListBox = new ListBox { Dock = DockStyle.Fill, IntegralHeight = false };
            _roomsListBox.DoubleClick += delegate { OnSidebarDoubleClick(); };
            _roomsListBox.MouseUp += RoomsListBoxOnMouseUp;
            sidebarPanel.Controls.Add(_roomsListBox);

            _roomsMenu = new ContextMenuStrip();
            ToolStripMenuItem leaveItem = new ToolStripMenuItem("Salir de la sala");
            leaveItem.Click += delegate { LeaveSelectedRoom(); };
            _roomsMenu.Items.Add(leaveItem);

            FlowLayoutPanel sidebarButtonsPanel = new FlowLayoutPanel
            {
                Dock = DockStyle.Bottom,
                AutoSize = true,
                FlowDirection = FlowDirection.LeftToRight,
                Padding = new Padding(0, 6, 0, 0)
            };
            sidebarPanel.Controls.Add(sidebarButtonsPanel);

            _showJoinedButton = new Button { Text = "Mis salas", Width = 110 };
            _showJoinedButton.Click += delegate { ShowJoinedRooms(); };
            sidebarButtonsPanel.Controls.Add(_showJoinedButton);

            _listPublicButton = new Button { Text = "Listar públicas", Width = 110 };
            _listPublicButton.Click += delegate { RequestRooms(); };
            sidebarButtonsPanel.Controls.Add(_listPublicButton);

            _createJoinButton = new Button { Text = "Crear / Unirse a sala", Dock = DockStyle.Bottom };
            _createJoinButton.Click += delegate { CreateOrJoinRoom(); };
            sidebarPanel.Controls.Add(_createJoinButton);

            Panel chatPanel = new Panel { Dock = DockStyle.Fill };
            mainPanel.Controls.Add(chatPanel);

            _activeRoomLabel = new Label
            {
                Text = "Sala activa: global",
                Dock = DockStyle.Top,
                Font = new System.Drawing.Font(Font, System.Drawing.FontStyle.Bold)
            };
            chatPanel.Controls.Add(_activeRoomLabel);

            _chatArea = new ChatRichTextBox
            {
                Dock = DockStyle.Fill,
                ReadOnly = true,
                HideSelection = false
            };
            _chatArea.ScrolledToTop += delegate { LoadMoreHistoryChunk(); };
            chatPanel.Controls.Add(_chatArea);

            Panel bottomPanel = new Panel { Dock = DockStyle.Bottom, Height = 40, Padding = new Padding(0, 6, 0, 0) };
            Controls.Add(bottomPanel);

            _messageEntry = new TextBox { Dock = DockStyle.Fill };
            _messageEntry.KeyDown += MessageEntryOnKeyDown;
            bottomPanel.Controls.Add(_messageEntry);

            _sendButton = new Button { Text = "Enviar", Dock = DockStyle.Right, Enabled = false, Width = 120 };
            _sendButton.Click += delegate { SendMessage(); };
            bottomPanel.Controls.Add(_sendButton);

            _serverStore.Load();
            UpdateServersCombo();

            RefreshSidebar();

            FormClosing += OnFormClosing;
        }

        private void RoomsListBoxOnMouseUp(object sender, MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Right || _sidebarMode != SidebarMode.Joined)
            {
                return;
            }

            int index = _roomsListBox.IndexFromPoint(e.Location);
            if (index < 0 || index >= _roomsListBox.Items.Count)
            {
                return;
            }

            _roomsListBox.SelectedIndex = index;
            object item = _roomsListBox.Items[index];
            string text = item != null ? item.ToString() : string.Empty;
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            text = text.Trim();
            string room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2) : text;
            if (string.Equals(room, "global", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            _roomsMenu.Show(_roomsListBox, e.Location);
        }

        private void MessageEntryOnKeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                e.Handled = true;
                e.SuppressKeyPress = true;
                SendMessage();
            }
        }

        private void OnServerSelected()
        {
            string alias = _serversCombo.SelectedItem as string;
            if (alias == null)
            {
                return;
            }

            ServerInfo info;
            if (_serverStore.Servers.TryGetValue(alias, out info))
            {
                _serverEntry.Text = info.Host;
                _portEntry.Text = info.Port.ToString();
            }
        }

        private void UpdateServersCombo()
        {
            _serversCombo.Items.Clear();
            List<string> keys = new List<string>(_serverStore.Servers.Keys);
            keys.Sort(StringComparer.OrdinalIgnoreCase);
            foreach (string key in keys)
            {
                _serversCombo.Items.Add(key);
            }
        }

        private void SaveCurrentServer()
        {
            string alias = PromptDialog.ShowDialog(this, "Guardar servidor", "Alias para este servidor:");
            if (string.IsNullOrWhiteSpace(alias))
            {
                return;
            }

            if (!int.TryParse(_portEntry.Text.Trim(), out int port))
            {
                MessageBox.Show(this, "Puerto inválido.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            ServerInfo info = new ServerInfo
            {
                Host = _serverEntry.Text.Trim(),
                Port = port
            };
            _serverStore.Servers[alias] = info;
            _serverStore.Save();
            UpdateServersCombo();
            _serversCombo.SelectedItem = alias;
            MessageBox.Show(this, string.Format("Servidor guardado como '{0}'", alias), "Guardado", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void Connect()
        {
            if (_client != null)
            {
                MessageBox.Show(this, "Ya estás conectado.", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            string host = _serverEntry.Text.Trim();
            if (!int.TryParse(_portEntry.Text.Trim(), out int port))
            {
                MessageBox.Show(this, "Puerto inválido.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            string username = _userEntry.Text.Trim();
            if (string.IsNullOrWhiteSpace(username))
            {
                MessageBox.Show(this, "Ingrese un nombre de usuario.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            try
            {
                TcpClient client = new TcpClient();
                client.Connect(host, port);
                NetworkStream stream = client.GetStream();
                stream.ReadTimeout = 2000;
                stream.WriteTimeout = 2000;

                _reader = new StreamReader(stream, Encoding.UTF8, false, 1024);
                _writer = new StreamWriter(stream, new UTF8Encoding(false));
                _writer.AutoFlush = true;

                string prompt = _reader.ReadLine() ?? string.Empty;
                if (prompt.IndexOf("NOMBRE", StringComparison.OrdinalIgnoreCase) < 0)
                {
                    MessageBox.Show(this, "El servidor no envió el prompt esperado.", "Aviso", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }

                _writer.WriteLine(username);

                _client = client;
                _running = true;
                _username = username;
                _serverKey = BuildServerKey(host, port);
                _currentRoom = "global";
                _visitedRooms.Clear();
                _visitedRooms.Add("global");
                _historyIndex.Clear();
                _publicRoomsCache.Clear();
                _roomPasswords.Clear();
                _pendingJoinRoom = null;
                _pendingJoinPassword = null;
                _sidebarMode = SidebarMode.Joined;

                _connectButton.Enabled = false;
                _sendButton.Enabled = true;

                LoadRoomHistoryInitial("global");
                AppendLocal(string.Format("[{0}] Conectado a {1}:{2} como {3}", NowTs(), host, port, username));
                RefreshSidebar();

                _listenerThread = new Thread(new ThreadStart(ListenLoop));
                _listenerThread.IsBackground = true;
                _listenerThread.Start();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "No se pudo conectar: " + ex.Message, "Error de conexión", MessageBoxButtons.OK, MessageBoxIcon.Error);
                CloseConnection();
            }
        }

        private void ListenLoop()
        {
            try
            {
                while (_running && _reader != null)
                {
                    string line;
                    try
                    {
                        line = _reader.ReadLine();
                    }
                    catch (IOException)
                    {
                        break;
                    }
                    catch (ObjectDisposedException)
                    {
                        break;
                    }

                    if (line == null)
                    {
                        break;
                    }

                    line = line.TrimEnd('\r');
                    if (line.Length == 0)
                    {
                        continue;
                    }

                    BeginInvoke(new Action(delegate { ProcessServerLine(line); }));
                }
            }
            finally
            {
                _running = false;
                BeginInvoke(new Action(delegate
                {
                    AppendLocal(string.Format("[{0}] Desconectado del servidor.", NowTs()), _currentRoom);
                    DisconnectUi();
                }));
            }
        }

        private void ProcessServerLine(string line)
        {
            if (line.StartsWith("Salas públicas disponibles", StringComparison.OrdinalIgnoreCase))
            {
                List<RoomListEntry> rooms = new List<RoomListEntry>();
                string[] parts = line.Split(new[] { ':' }, 2);
                if (parts.Length == 2)
                {
                    string[] tokens = parts[1].Split(',');
                    foreach (string token in tokens)
                    {
                        string item = token.Trim();
                        if (item.Length == 0)
                        {
                            continue;
                        }

                        bool empty = item.IndexOf("(vacía)", StringComparison.OrdinalIgnoreCase) >= 0;
                        string name = RemoveVacantTag(item).Trim();
                        rooms.Add(new RoomListEntry { Name = name, Empty = empty });
                    }
                }

                _publicRoomsCache.Clear();
                _publicRoomsCache.AddRange(rooms);
                _sidebarMode = SidebarMode.PublicList;
                RefreshSidebar();
                AppendLocal(string.Format("[{0}] {1}", NowTs(), line));
                return;
            }

            if (line.IndexOf("Te has unido a la sala", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                string room = ExtractRoomName(line);
                if (!string.IsNullOrEmpty(room))
                {
                    _currentRoom = room;
                    _visitedRooms.Add(room);
                    _activeRoomLabel.Text = "Sala activa: " + room;
                    LoadRoomHistoryInitial(room);
                    RefreshSidebar();
                    if (_pendingJoinPassword != null)
                    {
                        if (!string.IsNullOrEmpty(_pendingJoinPassword))
                        {
                            _roomPasswords[room] = _pendingJoinPassword;
                        }
                        else
                        {
                            _roomPasswords.Remove(room);
                        }
                    }
                    _pendingJoinRoom = null;
                    _pendingJoinPassword = null;
                }

                AppendLocal(string.Format("[{0}] {1}", NowTs(), line), _currentRoom);
                return;
            }

            if (line.IndexOf("Has salido de la sala", StringComparison.OrdinalIgnoreCase) >= 0 && line.IndexOf("Sala activa", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                string room = ExtractRoomName(line);
                string previous = _currentRoom;
                string newActive = ExtractActiveRoom(line);
                if (string.IsNullOrEmpty(newActive))
                {
                    newActive = "global";
                }

                _currentRoom = newActive;
                _activeRoomLabel.Text = "Sala activa: " + newActive;
                LoadRoomHistoryInitial(newActive);
                RefreshSidebar();

                if (!string.IsNullOrEmpty(room))
                {
                    AppendLocal(string.Format("[{0}] {1}", NowTs(), line), room);
                    if (!string.Equals(room, "global", StringComparison.OrdinalIgnoreCase))
                    {
                        _visitedRooms.Remove(room);
                        _historyIndex.Remove(room);
                        _roomPasswords.Remove(room);
                    }
                }

                AppendLocal(string.Format("[{0}] {1}", NowTs(), line), newActive);
                return;
            }

            if (line.IndexOf("Contraseña requerida", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                if (!string.IsNullOrEmpty(_pendingJoinRoom))
                {
                    string room = _pendingJoinRoom;
                    string promptPassword = PromptDialog.ShowDialog(this, "Contraseña requerida", "Ingresa la contraseña para '" + room + "':", true);
                    if (string.IsNullOrEmpty(promptPassword))
                    {
                        AppendLocal(string.Format("[{0}] No se ingresó contraseña. No se unió a '{1}'.", NowTs(), room), _currentRoom);
                    }
                    else
                    {
                        JoinRoom(room, promptPassword, true);
                    }
                }

                AppendLocal(string.Format("[{0}] {1}", NowTs(), line), _currentRoom);
                return;
            }

            AppendLocal(string.Format("[{0}] {1}", NowTs(), line), _currentRoom);
        }

        private static string ExtractRoomName(string line)
        {
            try
            {
                int start = line.IndexOf('\'');
                if (start < 0)
                {
                    return null;
                }

                start += 1;
                int end = line.IndexOf('\'', start);
                if (end < 0)
                {
                    return null;
                }

                return line.Substring(start, end - start);
            }
            catch
            {
                return null;
            }
        }

        private static string ExtractActiveRoom(string line)
        {
            const string marker = "Sala activa:";
            int idx = line.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
            if (idx < 0)
            {
                return null;
            }

            string fragment = line.Substring(idx + marker.Length).Trim();
            if (fragment.EndsWith("."))
            {
                fragment = fragment.Substring(0, fragment.Length - 1);
            }

            fragment = fragment.Trim();
            return string.IsNullOrEmpty(fragment) ? null : fragment;
        }

        private void SendMessage()
        {
            if (_client == null || _writer == null)
            {
                MessageBox.Show(this, "Conéctate al servidor primero.", "No conectado", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            string text = _messageEntry.Text.Trim();
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            if (text.StartsWith("/"))
            {
                HandleCommand(text);
            }
            else
            {
                try
                {
                    lock (_sendLock)
                    {
                        _writer.WriteLine(text);
                    }
                    AppendLocal(string.Format("[{0}] Tú: {1}", NowTs(), text), _currentRoom);
                }
                catch (Exception ex)
                {
                    AppendLocal(string.Format("[{0}] Error al enviar: {1}", NowTs(), ex.Message), _currentRoom);
                    DisconnectUi();
                }
            }

            _messageEntry.Clear();
        }

        private void HandleCommand(string text)
        {
            if (text.StartsWith("/join", StringComparison.OrdinalIgnoreCase))
            {
                IReadOnlyList<string> parts = CommandLineSplitter.Split(text);
                if (parts.Count < 2)
                {
                    AppendLocal("[Sistema] Uso: /join <sala> [password]", _currentRoom);
                    return;
                }

                string room = parts[1];
                string password = parts.Count > 2 ? parts[2] : null;
                JoinRoom(room, password);
            }
            else if (text.StartsWith("/leave", StringComparison.OrdinalIgnoreCase))
            {
                SendRaw(text);
            }
            else if (text.StartsWith("/rooms", StringComparison.OrdinalIgnoreCase))
            {
                RequestRooms();
            }
            else if (text.StartsWith("/quitar", StringComparison.OrdinalIgnoreCase))
            {
                Close();
            }
            else
            {
                AppendLocal("[Sistema] Comando desconocido.", _currentRoom);
            }
        }

        private void SendRaw(string raw)
        {
            if (_writer == null)
            {
                return;
            }

            try
            {
                lock (_sendLock)
                {
                    _writer.WriteLine(raw);
                }
            }
            catch (Exception ex)
            {
                AppendLocal(string.Format("[{0}] Error al enviar comando: {1}", NowTs(), ex.Message), _currentRoom);
            }
        }

        private static string FormatJoinCommand(string room, string password)
        {
            List<string> parts = new List<string> { "/join", Quote(room) };
            if (!string.IsNullOrEmpty(password))
            {
                parts.Add(Quote(password));
            }

            return string.Join(" ", parts.ToArray());
        }

        private static string FormatLeaveCommand(string room)
        {
            return "/leave " + Quote(room);
        }

        private static string Quote(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "''";
            }

            if (value.IndexOfAny(new[] { ' ', '\t', '\n', '\r', '\'', '"' }) < 0)
            {
                return value;
            }

            return "'" + value.Replace("'", "\\'") + "'";
        }

        private static string RemoveVacantTag(string text)
        {
            int index = text.IndexOf("(vacía)", StringComparison.OrdinalIgnoreCase);
            if (index < 0)
            {
                return text;
            }

            StringBuilder builder = new StringBuilder();
            builder.Append(text.Substring(0, index));
            int suffixIndex = index + "(vacía)".Length;
            if (suffixIndex < text.Length)
            {
                builder.Append(text.Substring(suffixIndex));
            }

            return builder.ToString();
        }

        private string BuildServerKey(string host, int port)
        {
            return host + ":" + port;
        }

        private void JoinRoom(string room, string password)
        {
            JoinRoom(room, password, false);
        }

        private void JoinRoom(string room, string password, bool silent)
        {
            if (string.IsNullOrWhiteSpace(room))
            {
                return;
            }

            string storedPassword = _roomPasswords.ContainsKey(room) ? _roomPasswords[room] : null;
            string effective = !string.IsNullOrEmpty(password) ? password : storedPassword;
            _pendingJoinRoom = room;
            _pendingJoinPassword = effective;
            string command = FormatJoinCommand(room, effective);
            if (!silent)
            {
                AppendLocal(string.Format("[{0}] Intentando unirse a '{1}'...", NowTs(), room), _currentRoom);
            }
            SendRaw(command);
        }

        private void SwitchToRoom(string room)
        {
            if (string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            JoinRoom(room, null);
        }

        private void CreateOrJoinRoom()
        {
            using (CreateJoinForm dialog = new CreateJoinForm())
            {
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    string room = dialog.RoomName != null ? dialog.RoomName.Trim() : string.Empty;
                    string password = dialog.Password != null ? dialog.Password.Trim() : string.Empty;
                    if (string.IsNullOrEmpty(room))
                    {
                        MessageBox.Show(this, "Debes escribir un nombre para la sala.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }

                    JoinRoom(room, string.IsNullOrEmpty(password) ? null : password);
                }
            }
        }

        private void RefreshSidebar()
        {
            _roomsListBox.BeginUpdate();
            _roomsListBox.Items.Clear();

            if (_sidebarMode == SidebarMode.Joined)
            {
                _sidebarTitle.Text = "Salas (doble clic para activar)";
                List<string> items = new List<string>();
                if (_visitedRooms.Contains("global"))
                {
                    items.Add("global");
                }

                foreach (string room in _visitedRooms.Where(r => !string.Equals(r, "global", StringComparison.OrdinalIgnoreCase)).OrderBy(r => r, StringComparer.OrdinalIgnoreCase))
                {
                    items.Add(room);
                }

                foreach (string room in items)
                {
                    string prefix = string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase) ? "• " : "  ";
                    _roomsListBox.Items.Add(prefix + room);
                }
            }
            else
            {
                _sidebarTitle.Text = "Salas públicas (doble clic para unirse)";
                if (_publicRoomsCache.Count == 0)
                {
                    _roomsListBox.Items.Add("(no hay salas públicas)");
                }
                else
                {
                    IEnumerable<RoomListEntry> ordered = _publicRoomsCache.OrderBy(delegate (RoomListEntry r) { return r.Name; }, StringComparer.OrdinalIgnoreCase);
                    foreach (RoomListEntry entry in ordered)
                    {
                        _roomsListBox.Items.Add(entry.Empty ? entry.Name + " (vacía)" : entry.Name);
                    }
                }
            }

            _roomsListBox.EndUpdate();
        }

        private void ShowJoinedRooms()
        {
            _sidebarMode = SidebarMode.Joined;
            RefreshSidebar();
        }

        private void RequestRooms()
        {
            _sidebarMode = SidebarMode.PublicList;
            _publicRoomsCache.Clear();
            RefreshSidebar();
            SendRaw("/rooms");
        }

        private void OnSidebarDoubleClick()
        {
            string text = _roomsListBox.SelectedItem as string;
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            text = text.Trim();
            if (_sidebarMode == SidebarMode.Joined)
            {
                string room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2) : text;
                SwitchToRoom(room);
            }
            else
            {
                if (text.Equals("(no hay salas públicas)", StringComparison.OrdinalIgnoreCase))
                {
                    return;
                }

                string room = RemoveVacantTag(text).Trim();
                JoinRoom(room, null);
            }
        }

        private void LeaveSelectedRoom()
        {
            string text = _roomsListBox.SelectedItem as string;
            if (string.IsNullOrEmpty(text))
            {
                return;
            }

            text = text.Trim();
            string room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2) : text;
            if (room.Equals("global", StringComparison.OrdinalIgnoreCase))
            {
                MessageBox.Show(this, "No podés salir de la sala global.", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            if (string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase))
            {
                SendRaw("/leave");
            }
            else
            {
                SendRaw(FormatLeaveCommand(room));
            }
        }

        private void LoadRoomHistoryInitial(string room)
        {
            string path = HistoryManager.HistoryPath(room, _serverKey);
            int startIndex;
            string[] lines = HistoryManager.TailLines(path, LoadChunk, out startIndex);
            _historyIndex[room] = new RoomHistoryState { StartIndex = startIndex };
            _chatArea.ReadOnly = false;
            _chatArea.Clear();
            foreach (string line in lines)
            {
                _chatArea.AppendText(line + Environment.NewLine);
            }
            _chatArea.ReadOnly = true;
            _chatArea.SelectionStart = _chatArea.TextLength;
            _chatArea.ScrollToCaret();
        }

        private void LoadMoreHistoryChunk()
        {
            string room = _currentRoom;
            RoomHistoryState state;
            if (!_historyIndex.TryGetValue(room, out state))
            {
                return;
            }

            int startIndex = state.StartIndex;
            if (startIndex == 0)
            {
                return;
            }

            string path = HistoryManager.HistoryPath(room, _serverKey);
            int newStart;
            string[] lines = HistoryManager.HeadChunk(path, startIndex, LoadChunk, out newStart);
            if (lines.Length == 0)
            {
                return;
            }

            StringBuilder builder = new StringBuilder();
            for (int i = 0; i < lines.Length; i++)
            {
                builder.Append(lines[i]);
                builder.Append(Environment.NewLine);
            }

            string textToInsert = builder.ToString();

            _chatArea.ReadOnly = false;
            _chatArea.SelectionStart = 0;
            _chatArea.SelectionLength = 0;
            _chatArea.SelectedText = textToInsert;
            _chatArea.SelectionStart = textToInsert.Length;
            _chatArea.ScrollToCaret();
            _chatArea.ReadOnly = true;

            state.StartIndex = newStart;
        }

        private void AppendLocal(string text)
        {
            AppendLocal(text, null);
        }

        private void AppendLocal(string text, string room)
        {
            string targetRoom = room ?? _currentRoom;
            HistoryManager.AppendHistoryLine(targetRoom, text, _serverKey);
            if (string.Equals(targetRoom, _currentRoom, StringComparison.OrdinalIgnoreCase))
            {
                _chatArea.ReadOnly = false;
                _chatArea.AppendText(text + Environment.NewLine);
                _chatArea.ReadOnly = true;
                _chatArea.SelectionStart = _chatArea.TextLength;
                _chatArea.ScrollToCaret();
            }
        }

        private static string NowTs()
        {
            return DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
        }

        private void DisconnectUi()
        {
            CloseConnection();
            _connectButton.Enabled = true;
            _sendButton.Enabled = false;
        }

        private void CloseConnection()
        {
            _running = false;

            if (_reader != null)
            {
                try
                {
                    _reader.Dispose();
                }
                catch
                {
                }
                _reader = null;
            }

            if (_writer != null)
            {
                try
                {
                    _writer.Dispose();
                }
                catch
                {
                }
                _writer = null;
            }

            if (_client != null)
            {
                try
                {
                    _client.Close();
                }
                catch
                {
                }
                _client = null;
            }
        }

        private void OnFormClosing(object sender, FormClosingEventArgs e)
        {
            _running = false;
            try
            {
                if (_writer != null)
                {
                    _writer.WriteLine("/quitar");
                }
            }
            catch
            {
            }
            CloseConnection();
        }

        private sealed class RoomHistoryState
        {
            public int StartIndex { get; set; }
        }

        private sealed class RoomListEntry
        {
            public string Name { get; set; } = string.Empty;
            public bool Empty { get; set; }
        }

        private enum SidebarMode
        {
            Joined,
            PublicList
        }
    }
}
