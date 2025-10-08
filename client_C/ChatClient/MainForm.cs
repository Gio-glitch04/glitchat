using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace ChatClient
{
    public partial class MainForm : Form
    {
        private const string DefaultHost = "127.0.0.1";
        private const int DefaultPort = 55555;
        private const int LoadChunk = 100;

        private readonly Dictionary<string, ServerInfo> _servers;
        private readonly HashSet<string> _visitedRooms = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, string> _roomPasswords = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, HistoryState> _historyIndex = new Dictionary<string, HistoryState>(StringComparer.OrdinalIgnoreCase);
        private readonly List<PublicRoom> _publicRooms = new List<PublicRoom>();

        private SidebarMode _sidebarMode = SidebarMode.Joined;
        private TcpClient _client;
        private NetworkStream _stream;
        private Thread _listenerThread;
        private volatile bool _running;
        private string _username;
        private string _serverKey = "default";
        private string _currentRoom = "global";
        private string _pendingJoinRoom;
        private string _pendingJoinPassword;

        private class HistoryState
        {
            public int StartIndex { get; set; }
        }

        private class PublicRoom
        {
            public PublicRoom(string name, bool isEmpty)
            {
                Name = name;
                IsEmpty = isEmpty;
            }

            public string Name { get; }
            public bool IsEmpty { get; }
        }

        private enum SidebarMode
        {
            Joined,
            PublicList
        }

        private const int EmGetFirstVisibleLine = 0xCE;

        [DllImport("user32.dll")]
        private static extern int SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);

        public MainForm()
        {
            InitializeComponent();

            serverTextBox.Text = DefaultHost;
            portTextBox.Text = DefaultPort.ToString();
            sendButton.Enabled = false;
            chatRichTextBox.ReadOnly = true;

            _servers = ServerStorage.LoadServers();
            serversComboBox.Items.AddRange(_servers.Keys.ToArray());

            _visitedRooms.Add("global");
            RefreshSidebar();
        }

        private void ConnectButton_Click(object sender, EventArgs e)
        {
            if (_client != null)
            {
                MessageBox.Show(this, "Ya estás conectado.", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }

            var host = serverTextBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(host))
            {
                MessageBox.Show(this, "Ingrese un servidor.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            if (!int.TryParse(portTextBox.Text.Trim(), out var port))
            {
                MessageBox.Show(this, "Puerto inválido.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            var username = userTextBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(username))
            {
                MessageBox.Show(this, "Ingrese un nombre de usuario.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            try
            {
                _client = new TcpClient();
                _client.Connect(host, port);
                _stream = _client.GetStream();
                _stream.ReadTimeout = 2000;

                var buffer = new byte[1024];
                int bytesRead = _stream.Read(buffer, 0, buffer.Length);
                if (bytesRead <= 0)
                {
                    throw new IOException("El servidor cerró la conexión durante el handshake.");
                }
                var prompt = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                if (!prompt.ToUpperInvariant().Contains("NOMBRE"))
                {
                    MessageBox.Show(this, "El servidor no envió el prompt esperado.", "Aviso", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                }

                var userBytes = Encoding.UTF8.GetBytes(username + "\n");
                _stream.Write(userBytes, 0, userBytes.Length);
                _stream.Flush();
                _stream.ReadTimeout = Timeout.Infinite;

                _username = username;
                _running = true;
                _serverKey = BuildServerKey(host, port);
                _historyIndex.Clear();
                _roomPasswords.Clear();
                _pendingJoinRoom = null;
                _pendingJoinPassword = null;
                _publicRooms.Clear();

                connectButton.Enabled = false;
                sendButton.Enabled = true;

                _currentRoom = "global";
                _visitedRooms.Clear();
                _visitedRooms.Add("global");
                _sidebarMode = SidebarMode.Joined;
                activeRoomLabel.Text = "Sala activa: global";
                LoadRoomHistoryInitial("global");
                AppendLocal(string.Format("[{0}] Conectado a {1}:{2} como {3}", NowTs(), host, port, username), "global");
                RefreshSidebar();

                _listenerThread = new Thread(ListenLoop)
                {
                    IsBackground = true
                };
                _listenerThread.Start();
            }
            catch (Exception ex)
            {
                MessageBox.Show(this, "No se pudo conectar: " + ex.Message, "Error de conexión", MessageBoxButtons.OK, MessageBoxIcon.Error);
                DisconnectUi();
            }
        }

        private void ListenLoop()
        {
            try
            {
                using (var reader = new StreamReader(_stream, Encoding.UTF8, false, 1024, true))
                {
                    string line;
                    while (_running && (line = reader.ReadLine()) != null)
                    {
                        var cleanLine = line.Trim('\r');
                        if (!string.IsNullOrWhiteSpace(cleanLine))
                        {
                            BeginInvoke(new Action(() => ProcessServerLine(cleanLine)));
                        }
                    }
                }
            }
            catch
            {
                // ignored - handled by finally
            }
            finally
            {
                _running = false;
                BeginInvoke(new Action(() =>
                {
                    AppendLocal(string.Format("[{0}] Desconectado del servidor.", NowTs()), _currentRoom);
                    DisconnectUi();
                }));
            }
        }

        private void ProcessServerLine(string line)
        {
            if (line.Equals("/rooms", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            if (line.StartsWith("Salas públicas disponibles", StringComparison.OrdinalIgnoreCase))
            {
                _sidebarMode = SidebarMode.PublicList;
                _publicRooms.Clear();
                var parts = line.Split(new[] { ':' }, 2);
                if (parts.Length == 2)
                {
                    var entries = parts[1].Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                    foreach (var entry in entries)
                    {
                        var trimmed = entry.Trim();
                        if (string.IsNullOrEmpty(trimmed))
                        {
                            continue;
                        }

                        var empty = trimmed.EndsWith("(vacía)", StringComparison.OrdinalIgnoreCase);
                        var name = empty ? trimmed.Replace("(vacía)", string.Empty).Trim() : trimmed;
                        _publicRooms.Add(new PublicRoom(name, empty));
                    }
                }

                RefreshSidebar();
                AppendLocal(string.Format("[{0}] {1}", NowTs(), line));
                return;
            }

            if ((line.Contains("sala '") && line.IndexOf("unid", StringComparison.OrdinalIgnoreCase) >= 0) ||
                line.IndexOf("estás ahora en la sala", StringComparison.OrdinalIgnoreCase) >= 0 ||
                line.IndexOf("ahora estás en la sala", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                var joinedRoom = ExtractBetween(line, "'", "'") ?? _pendingJoinRoom ?? _currentRoom;
                if (!string.IsNullOrEmpty(joinedRoom))
                {
                    _currentRoom = joinedRoom;
                    _visitedRooms.Add(joinedRoom);
                    activeRoomLabel.Text = "Sala activa: " + joinedRoom;
                    LoadRoomHistoryInitial(joinedRoom);
                    _sidebarMode = SidebarMode.Joined;
                    RefreshSidebar();
                    if (!string.IsNullOrEmpty(_pendingJoinRoom) && string.Equals(_pendingJoinRoom, joinedRoom, StringComparison.OrdinalIgnoreCase))
                    {
                        if (!string.IsNullOrEmpty(_pendingJoinPassword))
                        {
                            _roomPasswords[joinedRoom] = _pendingJoinPassword;
                        }
                        _pendingJoinRoom = null;
                        _pendingJoinPassword = null;
                    }
                }

                AppendLocal(string.Format("[{0}] {1}", NowTs(), line), joinedRoom);
                return;
            }

            if (line.Contains("Has salido de la sala"))
            {
                var leftRoom = ExtractBetween(line, "'", "'");
                if (!string.IsNullOrEmpty(leftRoom))
                {
                    _visitedRooms.Remove(leftRoom);
                    if (string.Equals(_currentRoom, leftRoom, StringComparison.OrdinalIgnoreCase))
                    {
                        _currentRoom = "global";
                        _visitedRooms.Add("global");
                        activeRoomLabel.Text = "Sala activa: global";
                        LoadRoomHistoryInitial("global");
                    }
                    RefreshSidebar();
                }

                AppendLocal(string.Format("[{0}] {1}", NowTs(), line));
                return;
            }

            if (line.Contains("❌ Contraseña incorrecta"))
            {
                var room = _pendingJoinRoom ?? _currentRoom;
                if (!string.IsNullOrEmpty(room))
                {
                    _roomPasswords.Remove(room);
                }

                var pwd = PromptDialog.Show(this, "Contraseña requerida", "Ingrese contraseña para la sala '" + room + "':", string.Empty, true);
                if (!string.IsNullOrEmpty(pwd))
                {
                    JoinRoom(room, pwd, true);
                }
                else
                {
                    AppendLocal(string.Format("[{0}] No se ingresó contraseña. No se unió a '{1}'.", NowTs(), room));
                }
                return;
            }

            if (line.Contains(":"))
            {
                AppendLocal(string.Format("[{0}] {1}", NowTs(), line));
                return;
            }

            AppendLocal(string.Format("[{0}] {1}", NowTs(), line));
        }

        private void SendButton_Click(object sender, EventArgs e)
        {
            SendMessageFromInput();
        }

        private void MessageTextBox_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                e.SuppressKeyPress = true;
                SendMessageFromInput();
            }
        }

        private void SendMessageFromInput()
        {
            if (_client == null || !_client.Connected)
            {
                MessageBox.Show(this, "Conéctate al servidor primero.", "No conectado", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var text = messageTextBox.Text.Trim();
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
                    var data = Encoding.UTF8.GetBytes(text + "\n");
                    _stream.Write(data, 0, data.Length);
                    _stream.Flush();
                    AppendLocal(string.Format("[{0}] Tú: {1}", NowTs(), text));
                }
                catch (Exception ex)
                {
                    AppendLocal(string.Format("[{0}] Error al enviar: {1}", NowTs(), ex.Message));
                    _running = false;
                    DisconnectUi();
                }
            }

            messageTextBox.Clear();
        }

        private void HandleCommand(string text)
        {
            var lower = text.ToLowerInvariant();
            if (lower.StartsWith("/join"))
            {
                var parts = SplitCommand(text);
                if (parts.Length < 2)
                {
                    AppendLocal("[Sistema] Uso: /join <sala> [password]");
                }
                else
                {
                    var room = parts[1];
                    var pwd = parts.Length > 2 ? parts[2] : null;
                    JoinRoom(room, pwd);
                }
            }
            else if (lower.StartsWith("/leave"))
            {
                SendRaw(text);
            }
            else if (lower.StartsWith("/rooms"))
            {
                RequestRooms();
            }
            else if (lower.StartsWith("/quitar"))
            {
                Close();
            }
            else
            {
                AppendLocal("[Sistema] Comando desconocido.");
            }
        }

        private void JoinRoom(string room, string password = null, bool silent = false)
        {
            if (string.IsNullOrWhiteSpace(room))
            {
                return;
            }

            _pendingJoinRoom = room;
            _pendingJoinPassword = string.IsNullOrEmpty(password) && _roomPasswords.ContainsKey(room)
                ? _roomPasswords[room]
                : password;

            if (!silent)
            {
                AppendLocal(string.Format("[{0}] Intentando unirse a '{1}'...", NowTs(), room));
            }

            var cmd = FormatJoinCommand(room, _pendingJoinPassword);
            SendRaw(cmd);
        }

        private void RequestRooms()
        {
            _sidebarMode = SidebarMode.PublicList;
            _publicRooms.Clear();
            RefreshSidebar();
            SendRaw("/rooms");
        }

        private void SendRaw(string command)
        {
            if (_client == null || !_client.Connected)
            {
                return;
            }

            try
            {
                var data = Encoding.UTF8.GetBytes(command + "\n");
                _stream.Write(data, 0, data.Length);
                _stream.Flush();
            }
            catch (Exception ex)
            {
                AppendLocal(string.Format("[{0}] Error al enviar comando: {1}", NowTs(), ex.Message));
            }
        }

        private static string[] SplitCommand(string text)
        {
            var parts = new List<string>();
            var current = new StringBuilder();
            bool inQuotes = false;
            for (int i = 0; i < text.Length; i++)
            {
                var c = text[i];
                if (c == '"')
                {
                    inQuotes = !inQuotes;
                    continue;
                }

                if (!inQuotes && char.IsWhiteSpace(c))
                {
                    if (current.Length > 0)
                    {
                        parts.Add(current.ToString());
                        current.Clear();
                    }
                }
                else
                {
                    current.Append(c);
                }
            }

            if (current.Length > 0)
            {
                parts.Add(current.ToString());
            }

            return parts.ToArray();
        }

        private void LoadRoomHistoryInitial(string room)
        {
            var path = HistoryManager.HistoryPath(room, _serverKey);
            var tuple = HistoryManager.TailLines(path, LoadChunk);
            var lines = tuple.Item1;
            var startIdx = tuple.Item2;
            _historyIndex[room] = new HistoryState { StartIndex = startIdx };

            chatRichTextBox.SuspendLayout();
            chatRichTextBox.Clear();
            foreach (var line in lines)
            {
                chatRichTextBox.AppendText(line);
            }
            if (lines.Count > 0 && !lines.Last().EndsWith("\n"))
            {
                chatRichTextBox.AppendText(Environment.NewLine);
            }
            chatRichTextBox.SelectionStart = chatRichTextBox.TextLength;
            chatRichTextBox.ScrollToCaret();
            chatRichTextBox.ResumeLayout();
        }

        private void LoadMoreHistoryChunk()
        {
            if (!_historyIndex.TryGetValue(_currentRoom, out var state))
            {
                return;
            }

            if (state.StartIndex == 0)
            {
                return;
            }

            var path = HistoryManager.HistoryPath(_currentRoom, _serverKey);
            var tuple = HistoryManager.HeadChunk(path, state.StartIndex, LoadChunk);
            var lines = tuple.Item1;
            var newStart = tuple.Item2;
            if (lines.Count == 0)
            {
                return;
            }

            var currentSelection = chatRichTextBox.SelectionStart;
            chatRichTextBox.SuspendLayout();
            chatRichTextBox.Text = string.Join(string.Empty, lines) + chatRichTextBox.Text;
            var index = chatRichTextBox.GetFirstCharIndexFromLine(lines.Count);
            if (index < 0)
            {
                index = 0;
            }
            chatRichTextBox.SelectionStart = index;
            chatRichTextBox.ScrollToCaret();
            chatRichTextBox.ResumeLayout();
            state.StartIndex = newStart;
        }

        private void AppendLocal(string text, string room = null)
        {
            var targetRoom = room ?? _currentRoom;
            HistoryManager.AppendHistoryLine(targetRoom, text, _serverKey);
            if (string.Equals(targetRoom, _currentRoom, StringComparison.OrdinalIgnoreCase))
            {
                chatRichTextBox.AppendText(text + Environment.NewLine);
                chatRichTextBox.SelectionStart = chatRichTextBox.TextLength;
                chatRichTextBox.ScrollToCaret();
            }
        }

        private void RefreshSidebar()
        {
            roomsListBox.BeginUpdate();
            roomsListBox.Items.Clear();

            if (_sidebarMode == SidebarMode.Joined)
            {
                sidebarTitleLabel.Text = "Salas (doble clic para activar)";
                var items = new List<string>();
                if (_visitedRooms.Contains("global"))
                {
                    items.Add("global");
                }
                items.AddRange(_visitedRooms.Where(r => !string.Equals(r, "global", StringComparison.OrdinalIgnoreCase)).OrderBy(r => r, StringComparer.OrdinalIgnoreCase));
                foreach (var room in items)
                {
                    var prefix = string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase) ? "• " : "  ";
                    roomsListBox.Items.Add(prefix + room);
                }
            }
            else
            {
                sidebarTitleLabel.Text = "Salas públicas (doble clic para unirse)";
                if (_publicRooms.Count == 0)
                {
                    roomsListBox.Items.Add("(no hay salas públicas)");
                }
                else
                {
                    foreach (var room in _publicRooms.OrderBy(r => r.Name, StringComparer.OrdinalIgnoreCase))
                    {
                        roomsListBox.Items.Add(room.IsEmpty ? room.Name + " (vacía)" : room.Name);
                    }
                }
            }

            roomsListBox.EndUpdate();
        }

        private void RoomsListBox_DrawItem(object sender, DrawItemEventArgs e)
        {
            e.DrawBackground();
            if (e.Index < 0 || e.Index >= roomsListBox.Items.Count)
            {
                return;
            }

            var text = roomsListBox.Items[e.Index].ToString();
            var isSelected = (e.State & DrawItemState.Selected) == DrawItemState.Selected;
            var color = isSelected ? SystemColors.HighlightText : SystemColors.ControlText;
            if (_sidebarMode == SidebarMode.PublicList && text.EndsWith("(vacía)", StringComparison.OrdinalIgnoreCase) && !isSelected)
            {
                color = Color.Gray;
            }

            using (var brush = new SolidBrush(color))
            {
                e.Graphics.DrawString(text, e.Font, brush, e.Bounds);
            }
            e.DrawFocusRectangle();
        }

        private void RoomsListBox_DoubleClick(object sender, EventArgs e)
        {
            if (roomsListBox.SelectedItem == null)
            {
                return;
            }

            var text = roomsListBox.SelectedItem.ToString().Trim();
            if (_sidebarMode == SidebarMode.Joined)
            {
                var room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2).Trim() : text;
                if (!string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase))
                {
                    JoinRoom(room);
                }
            }
            else
            {
                if (text == "(no hay salas públicas)")
                {
                    return;
                }
                var room = text.Replace("(vacía)", string.Empty).Trim();
                JoinRoom(room);
            }
        }

        private void RoomsListBox_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Right)
            {
                var index = roomsListBox.IndexFromPoint(e.Location);
                if (index >= 0)
                {
                    roomsListBox.SelectedIndex = index;
                }
            }
        }

        private void RoomsContextMenu_Opening(object sender, System.ComponentModel.CancelEventArgs e)
        {
            if (_sidebarMode != SidebarMode.Joined || roomsListBox.SelectedItem == null)
            {
                e.Cancel = true;
            }
        }

        private void LeaveRoomMenuItem_Click(object sender, EventArgs e)
        {
            if (_sidebarMode != SidebarMode.Joined)
            {
                return;
            }

            if (roomsListBox.SelectedItem == null)
            {
                return;
            }

            var text = roomsListBox.SelectedItem.ToString().Trim();
            var room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2).Trim() : text;
            if (string.Equals(room, "global", StringComparison.OrdinalIgnoreCase))
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

        private void JoinedRoomsButton_Click(object sender, EventArgs e)
        {
            _sidebarMode = SidebarMode.Joined;
            RefreshSidebar();
        }

        private void PublicRoomsButton_Click(object sender, EventArgs e)
        {
            RequestRooms();
        }

        private void CreateJoinButton_Click(object sender, EventArgs e)
        {
            using (var dialog = new CreateJoinRoomDialog())
            {
                if (dialog.ShowDialog(this) == DialogResult.OK)
                {
                    JoinRoom(dialog.RoomName, string.IsNullOrEmpty(dialog.Password) ? null : dialog.Password);
                }
            }
        }

        private void ChatRichTextBox_VScroll(object sender, EventArgs e)
        {
            var line = SendMessage(chatRichTextBox.Handle, EmGetFirstVisibleLine, IntPtr.Zero, IntPtr.Zero);
            if (line <= 0)
            {
                LoadMoreHistoryChunk();
            }
        }

        private void ServersComboBox_SelectedIndexChanged(object sender, EventArgs e)
        {
            var name = serversComboBox.SelectedItem as string;
            if (name != null && _servers.TryGetValue(name, out var info))
            {
                serverTextBox.Text = info.Host ?? DefaultHost;
                portTextBox.Text = info.Port.ToString();
            }
        }

        private void SaveServerButton_Click(object sender, EventArgs e)
        {
            var alias = PromptDialog.Show(this, "Guardar servidor", "Alias para este servidor:");
            if (string.IsNullOrWhiteSpace(alias))
            {
                return;
            }

            if (!int.TryParse(portTextBox.Text.Trim(), out var port))
            {
                MessageBox.Show(this, "Puerto inválido.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            var host = serverTextBox.Text.Trim();
            _servers[alias] = new ServerInfo { Host = host, Port = port };
            ServerStorage.SaveServers(_servers);
            serversComboBox.Items.Clear();
            serversComboBox.Items.AddRange(_servers.Keys.ToArray());
            serversComboBox.SelectedItem = alias;
            MessageBox.Show(this, "Servidor guardado como '" + alias + "'", "Guardado", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void DisconnectUi()
        {
            _running = false;
            sendButton.Enabled = false;
            connectButton.Enabled = true;
            if (_stream != null)
            {
                try
                {
                    _stream.Dispose();
                }
                catch
                {
                    // ignore
                }
                _stream = null;
            }

            if (_client != null)
            {
                try
                {
                    _client.Close();
                }
                catch
                {
                    // ignore
                }
                _client = null;
            }
            _listenerThread = null;
        }

        private void MainForm_FormClosing(object sender, FormClosingEventArgs e)
        {
            _running = false;
            try
            {
                _stream?.Close();
            }
            catch
            {
                // ignore
            }
            try
            {
                _client?.Close();
            }
            catch
            {
                // ignore
            }
        }

        private static string FormatJoinCommand(string room, string password)
        {
            if (string.IsNullOrEmpty(password))
            {
                return "/join " + QuoteIfNeeded(room);
            }

            return "/join " + QuoteIfNeeded(room) + " " + QuoteIfNeeded(password);
        }

        private static string FormatLeaveCommand(string room)
        {
            return "/leave " + QuoteIfNeeded(room);
        }

        private static string QuoteIfNeeded(string value)
        {
            if (string.IsNullOrEmpty(value))
            {
                return "";
            }

            if (value.IndexOf(' ') >= 0)
            {
                return '"' + value.Replace("\"", "\\\"") + '"';
            }

            return value;
        }

        private static string BuildServerKey(string host, int port)
        {
            return host + ":" + port;
        }

        private static string NowTs()
        {
            return DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");
        }

        private static string ExtractBetween(string input, string start, string end)
        {
            var startIdx = input.IndexOf(start, StringComparison.Ordinal);
            if (startIdx < 0)
            {
                return null;
            }

            startIdx += start.Length;
            var endIdx = input.IndexOf(end, startIdx, StringComparison.Ordinal);
            if (endIdx < 0)
            {
                return null;
            }

            return input.Substring(startIdx, endIdx - startIdx);
        }

        private sealed class CreateJoinRoomDialog : Form
        {
            private readonly TextBox _nameTextBox;
            private readonly TextBox _passwordTextBox;
            private readonly Button _okButton;

            public string RoomName => _nameTextBox.Text.Trim();
            public string Password => _passwordTextBox.Text.Trim();

            public CreateJoinRoomDialog()
            {
                Text = "Crear / Unirse a sala";
                FormBorderStyle = FormBorderStyle.FixedDialog;
                MaximizeBox = false;
                MinimizeBox = false;
                StartPosition = FormStartPosition.CenterParent;
                ClientSize = new Size(320, 150);

                var nameLabel = new Label
                {
                    Text = "Nombre de la sala:",
                    Location = new Point(12, 15),
                    AutoSize = true
                };
                Controls.Add(nameLabel);

                _nameTextBox = new TextBox
                {
                    Location = new Point(150, 12),
                    Width = 150
                };
                Controls.Add(_nameTextBox);

                var pwdLabel = new Label
                {
                    Text = "Contraseña (opcional):",
                    Location = new Point(12, 55),
                    AutoSize = true
                };
                Controls.Add(pwdLabel);

                _passwordTextBox = new TextBox
                {
                    Location = new Point(150, 52),
                    Width = 150,
                    UseSystemPasswordChar = true
                };
                Controls.Add(_passwordTextBox);

                _okButton = new Button
                {
                    Text = "Aceptar",
                    DialogResult = DialogResult.OK,
                    Location = new Point(110, 100),
                    Size = new Size(90, 27)
                };
                _okButton.Click += OkButton_Click;
                Controls.Add(_okButton);

                var cancelButton = new Button
                {
                    Text = "Cancelar",
                    DialogResult = DialogResult.Cancel,
                    Location = new Point(210, 100),
                    Size = new Size(90, 27)
                };
                Controls.Add(cancelButton);

                AcceptButton = _okButton;
                CancelButton = cancelButton;
            }

            private void OkButton_Click(object sender, EventArgs e)
            {
                if (string.IsNullOrWhiteSpace(RoomName))
                {
                    MessageBox.Show(this, "Debes escribir un nombre para la sala.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    DialogResult = DialogResult.None;
                    return;
                }
            }
        }
    }
}
