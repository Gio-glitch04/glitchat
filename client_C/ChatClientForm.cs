using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Windows.Forms;

namespace ClientC;

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

    private readonly ServerStore _serverStore = new();

    private TcpClient? _client;
    private StreamReader? _reader;
    private StreamWriter? _writer;
    private Thread? _listenerThread;
    private volatile bool _running;
    private string _username = string.Empty;
    private string _serverKey = "default";
    private string _currentRoom = "global";
    private SidebarMode _sidebarMode = SidebarMode.Joined;
    private readonly HashSet<string> _visitedRooms = new(StringComparer.OrdinalIgnoreCase) { "global" };
    private readonly Dictionary<string, RoomHistoryState> _historyIndex = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<(string Name, bool Empty)> _publicRoomsCache = new();
    private readonly Dictionary<string, string> _roomPasswords = new(StringComparer.OrdinalIgnoreCase);
    private string? _pendingJoinRoom;
    private string? _pendingJoinPassword;

    private readonly object _sendLock = new();

    public ChatClientForm()
    {
        Text = "Chat - Cliente (Windows Forms)";
        Width = 980;
        Height = 560;

        var topPanel = new FlowLayoutPanel
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
        _connectButton.Click += (_, _) => Connect();
        topPanel.Controls.Add(_connectButton);

        topPanel.Controls.Add(new Label { Text = "Recientes:", AutoSize = true, Margin = new Padding(12, 0, 0, 0) });
        _serversCombo = new ComboBox { Width = 150, DropDownStyle = ComboBoxStyle.DropDownList };
        _serversCombo.SelectedIndexChanged += (_, _) => OnServerSelected();
        topPanel.Controls.Add(_serversCombo);

        _saveServerButton = new Button { Text = "Guardar servidor...", Margin = new Padding(8, 0, 0, 0) };
        _saveServerButton.Click += (_, _) => SaveCurrentServer();
        topPanel.Controls.Add(_saveServerButton);

        Controls.Add(topPanel);

        var mainPanel = new Panel { Dock = DockStyle.Fill, Padding = new Padding(8, 0, 8, 6) };
        Controls.Add(mainPanel);

        var sidebarPanel = new Panel { Dock = DockStyle.Left, Width = 240, Padding = new Padding(0, 0, 8, 0) };
        mainPanel.Controls.Add(sidebarPanel);

        _sidebarTitle = new Label { Text = "Salas (doble clic para activar)", Dock = DockStyle.Top, AutoSize = true };
        sidebarPanel.Controls.Add(_sidebarTitle);

        _roomsListBox = new ListBox { Dock = DockStyle.Fill, IntegralHeight = false };
        _roomsListBox.DoubleClick += (_, _) => OnSidebarDoubleClick();
        _roomsListBox.MouseUp += RoomsListBoxOnMouseUp;
        sidebarPanel.Controls.Add(_roomsListBox);

        _roomsMenu = new ContextMenuStrip();
        var leaveItem = new ToolStripMenuItem("Salir de la sala");
        leaveItem.Click += (_, _) => LeaveSelectedRoom();
        _roomsMenu.Items.Add(leaveItem);

        var sidebarButtonsPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            AutoSize = true,
            FlowDirection = FlowDirection.LeftToRight,
            Padding = new Padding(0, 6, 0, 0)
        };
        sidebarPanel.Controls.Add(sidebarButtonsPanel);

        _showJoinedButton = new Button { Text = "Mis salas", Width = 110 };
        _showJoinedButton.Click += (_, _) => ShowJoinedRooms();
        sidebarButtonsPanel.Controls.Add(_showJoinedButton);

        _listPublicButton = new Button { Text = "Listar públicas", Width = 110 };
        _listPublicButton.Click += (_, _) => RequestRooms();
        sidebarButtonsPanel.Controls.Add(_listPublicButton);

        _createJoinButton = new Button { Text = "Crear / Unirse a sala", Dock = DockStyle.Bottom };
        _createJoinButton.Click += (_, _) => CreateOrJoinRoom();
        sidebarPanel.Controls.Add(_createJoinButton);

        var chatPanel = new Panel { Dock = DockStyle.Fill };
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
        _chatArea.ScrolledToTop += (_, _) => LoadMoreHistoryChunk();
        chatPanel.Controls.Add(_chatArea);

        var bottomPanel = new Panel { Dock = DockStyle.Bottom, Height = 40, Padding = new Padding(0, 6, 0, 0) };
        Controls.Add(bottomPanel);

        _messageEntry = new TextBox { Dock = DockStyle.Fill };
        _messageEntry.KeyDown += MessageEntryOnKeyDown;
        bottomPanel.Controls.Add(_messageEntry);

        _sendButton = new Button { Text = "Enviar", Dock = DockStyle.Right, Enabled = false, Width = 120 };
        _sendButton.Click += (_, _) => SendMessage();
        bottomPanel.Controls.Add(_sendButton);

        _serverStore.Load();
        UpdateServersCombo();

        RefreshSidebar();

        FormClosing += OnFormClosing;
    }

    private void RoomsListBoxOnMouseUp(object? sender, MouseEventArgs e)
    {
        if (e.Button != MouseButtons.Right || _sidebarMode != SidebarMode.Joined)
        {
            return;
        }

        var index = _roomsListBox.IndexFromPoint(e.Location);
        if (index < 0 || index >= _roomsListBox.Items.Count)
        {
            return;
        }

        _roomsListBox.SelectedIndex = index;
        var text = _roomsListBox.Items[index]?.ToString()?.Trim() ?? string.Empty;
        var room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2) : text;
        if (string.Equals(room, "global", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        _roomsMenu.Show(_roomsListBox, e.Location);
    }

    private void MessageEntryOnKeyDown(object? sender, KeyEventArgs e)
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
        if (_serversCombo.SelectedItem is not string alias)
        {
            return;
        }

        if (_serverStore.Servers.TryGetValue(alias, out var info))
        {
            _serverEntry.Text = info.Host;
            _portEntry.Text = info.Port.ToString();
        }
    }

    private void UpdateServersCombo()
    {
        _serversCombo.Items.Clear();
        foreach (var key in _serverStore.Servers.Keys.OrderBy(k => k, StringComparer.OrdinalIgnoreCase))
        {
            _serversCombo.Items.Add(key);
        }
    }

    private void SaveCurrentServer()
    {
        var alias = PromptDialog.ShowDialog(this, "Guardar servidor", "Alias para este servidor:");
        if (string.IsNullOrWhiteSpace(alias))
        {
            return;
        }

        if (!int.TryParse(_portEntry.Text.Trim(), out var port))
        {
            MessageBox.Show(this, "Puerto inválido.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        var info = new ServerInfo
        {
            Host = _serverEntry.Text.Trim(),
            Port = port
        };
        _serverStore.Servers[alias] = info;
        _serverStore.Save();
        UpdateServersCombo();
        _serversCombo.SelectedItem = alias;
        MessageBox.Show(this, $"Servidor guardado como '{alias}'", "Guardado", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    private void Connect()
    {
        if (_client != null)
        {
            MessageBox.Show(this, "Ya estás conectado.", "Info", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        var host = _serverEntry.Text.Trim();
        if (!int.TryParse(_portEntry.Text.Trim(), out var port))
        {
            MessageBox.Show(this, "Puerto inválido.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        var username = _userEntry.Text.Trim();
        if (string.IsNullOrWhiteSpace(username))
        {
            MessageBox.Show(this, "Ingrese un nombre de usuario.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        try
        {
            var client = new TcpClient();
            client.Connect(host, port);
            var stream = client.GetStream();
            stream.ReadTimeout = 2000;
            stream.WriteTimeout = 2000;

            _reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: false, bufferSize: 1024, leaveOpen: true);
            _writer = new StreamWriter(stream, new UTF8Encoding(false))
            {
                AutoFlush = true
            };

            var prompt = _reader.ReadLine() ?? string.Empty;
            if (!prompt.Contains("NOMBRE", StringComparison.OrdinalIgnoreCase))
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
            AppendLocal($"[{NowTs()}] Conectado a {host}:{port} como {username}");
            RefreshSidebar();

            _listenerThread = new Thread(ListenLoop) { IsBackground = true };
            _listenerThread.Start();
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"No se pudo conectar: {ex.Message}", "Error de conexión", MessageBoxButtons.OK, MessageBoxIcon.Error);
            CloseConnection();
        }
    }

    private void ListenLoop()
    {
        try
        {
            while (_running && _reader != null)
            {
                string? line;
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

                BeginInvoke(new Action(() => ProcessServerLine(line)));
            }
        }
        finally
        {
            _running = false;
            BeginInvoke(new Action(() =>
            {
                AppendLocal($"[{NowTs()}] Desconectado del servidor.", _currentRoom);
                DisconnectUi();
            }));
        }
    }

    private void ProcessServerLine(string line)
    {
        if (line.StartsWith("Salas públicas disponibles", StringComparison.OrdinalIgnoreCase))
        {
            var rooms = new List<(string Name, bool Empty)>();
            var parts = line.Split(':', 2);
            if (parts.Length == 2)
            {
                foreach (var token in parts[1].Split(','))
                {
                    var item = token.Trim();
                    if (string.IsNullOrEmpty(item))
                    {
                        continue;
                    }

                    var empty = item.IndexOf("(vacía)", StringComparison.OrdinalIgnoreCase) >= 0;
                    var name = RemoveVacantTag(item).Trim();
                    rooms.Add((name, empty));
                }
            }

            _publicRoomsCache.Clear();
            _publicRoomsCache.AddRange(rooms);
            _sidebarMode = SidebarMode.PublicList;
            RefreshSidebar();
            AppendLocal($"[{NowTs()}] {line}");
            return;
        }

        if (line.Contains("Te has unido a la sala", StringComparison.OrdinalIgnoreCase))
        {
            var room = ExtractRoomName(line);
            if (!string.IsNullOrEmpty(room))
            {
                _currentRoom = room;
                _visitedRooms.Add(room);
                _activeRoomLabel.Text = $"Sala activa: {room}";
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

            AppendLocal($"[{NowTs()}] {line}", _currentRoom);
            return;
        }

        if (line.Contains("Has salido de la sala", StringComparison.OrdinalIgnoreCase) && line.Contains("Sala activa", StringComparison.OrdinalIgnoreCase))
        {
            var room = ExtractRoomName(line);
            var previous = _currentRoom;
            var newActive = ExtractActiveRoom(line) ?? "global";
            _currentRoom = newActive;
            _visitedRooms.Add(newActive);
            if (!string.IsNullOrEmpty(room))
            {
                _visitedRooms.Remove(room);
                _historyIndex.Remove(room);
            }

            _activeRoomLabel.Text = $"Sala activa: {newActive}";
            if (!string.Equals(previous, newActive, StringComparison.OrdinalIgnoreCase))
            {
                LoadRoomHistoryInitial(newActive);
            }
            RefreshSidebar();
            AppendLocal($"[{NowTs()}] {line}", newActive);
            return;
        }

        if (line.Contains("Has vuelto al chat global", StringComparison.OrdinalIgnoreCase) ||
            line.Contains("No puedes salir del chat global", StringComparison.OrdinalIgnoreCase))
        {
            _currentRoom = "global";
            _visitedRooms.Add("global");
            _activeRoomLabel.Text = "Sala activa: global";
            LoadRoomHistoryInitial("global");
            RefreshSidebar();
            AppendLocal($"[{NowTs()}] {line}", "global");
            return;
        }

        if (line.Contains("❌ Contraseña incorrecta", StringComparison.OrdinalIgnoreCase))
        {
            var room = _pendingJoinRoom ?? _currentRoom;
            if (!string.IsNullOrEmpty(room))
            {
                _roomPasswords.Remove(room);
            }

            var password = PromptDialog.ShowDialog(this, "Contraseña requerida", $"Ingrese contraseña para la sala '{room}':", password: true);
            if (!string.IsNullOrEmpty(password))
            {
                var cmd = FormatJoinCommand(room ?? string.Empty, password);
                SendRaw(cmd);
            }
            else
            {
                AppendLocal($"[{NowTs()}] No se ingresó contraseña. No se unió a '{room}'.", _currentRoom);
            }
            return;
        }

        if (line.Contains(':'))
        {
            AppendLocal($"[{NowTs()}] {line}", _currentRoom);
            return;
        }

        AppendLocal($"[{NowTs()}] {line}", _currentRoom);
    }

    private static string? ExtractRoomName(string line)
    {
        try
        {
            var start = line.IndexOf('\'');
            if (start < 0)
            {
                return null;
            }

            start += 1;
            var end = line.IndexOf('\'', start);
            if (end < 0)
            {
                return null;
            }

            return line[start..end];
        }
        catch
        {
            return null;
        }
    }

    private static string? ExtractActiveRoom(string line)
    {
        var marker = "Sala activa:";
        var idx = line.IndexOf(marker, StringComparison.OrdinalIgnoreCase);
        if (idx < 0)
        {
            return null;
        }

        var fragment = line[(idx + marker.Length)..].Trim();
        if (fragment.EndsWith('.'))
        {
            fragment = fragment[..^1];
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

        var text = _messageEntry.Text.Trim();
        if (string.IsNullOrEmpty(text))
        {
            return;
        }

        if (text.StartsWith('/'))
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
                AppendLocal($"[{NowTs()}] Tú: {text}", _currentRoom);
            }
            catch (Exception ex)
            {
                AppendLocal($"[{NowTs()}] Error al enviar: {ex.Message}", _currentRoom);
                DisconnectUi();
            }
        }

        _messageEntry.Clear();
    }

    private void HandleCommand(string text)
    {
        if (text.StartsWith("/join", StringComparison.OrdinalIgnoreCase))
        {
            var parts = CommandLineSplitter.Split(text);
            if (parts.Count < 2)
            {
                AppendLocal("[Sistema] Uso: /join <sala> [password]", _currentRoom);
                return;
            }

            var room = parts[1];
            var password = parts.Count > 2 ? parts[2] : null;
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
            AppendLocal($"[{NowTs()}] Error al enviar comando: {ex.Message}", _currentRoom);
        }
    }

    private static string FormatJoinCommand(string room, string? password)
    {
        var parts = new List<string> { "/join", Quote(room) };
        if (!string.IsNullOrEmpty(password))
        {
            parts.Add(Quote(password));
        }

        return string.Join(' ', parts);
    }

    private static string FormatLeaveCommand(string room)
    {
        return $"/leave {Quote(room)}";
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

        return "'" + value.Replace("'", "\\'", StringComparison.Ordinal) + "'";
    }

    private static string RemoveVacantTag(string text)
    {
        var index = text.IndexOf("(vacía)", StringComparison.OrdinalIgnoreCase);
        if (index < 0)
        {
            return text;
        }

        var builder = new StringBuilder();
        builder.Append(text.AsSpan(0, index));
        builder.Append(text.AsSpan(index + "(vacía)".Length));
        return builder.ToString();
    }

    private string BuildServerKey(string host, int port)
    {
        return $"{host}:{port}";
    }

    private void JoinRoom(string room, string? password = null, bool silent = false)
    {
        if (string.IsNullOrWhiteSpace(room))
        {
            return;
        }

        var storedPassword = _roomPasswords.TryGetValue(room, out var stored) ? stored : null;
        var effective = !string.IsNullOrEmpty(password) ? password : storedPassword;
        _pendingJoinRoom = room;
        _pendingJoinPassword = effective;
        var command = FormatJoinCommand(room, effective);
        if (!silent)
        {
            AppendLocal($"[{NowTs()}] Intentando unirse a '{room}'...", _currentRoom);
        }
        SendRaw(command);
    }

    private void SwitchToRoom(string room)
    {
        if (string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        JoinRoom(room);
    }

    private void CreateOrJoinRoom()
    {
        using var dialog = new CreateJoinForm();
        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            var room = dialog.RoomName?.Trim();
            var password = dialog.Password?.Trim();
            if (string.IsNullOrEmpty(room))
            {
                MessageBox.Show(this, "Debes escribir un nombre para la sala.", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }

            JoinRoom(room, string.IsNullOrEmpty(password) ? null : password);
        }
    }

    private void RefreshSidebar()
    {
        _roomsListBox.BeginUpdate();
        _roomsListBox.Items.Clear();

        if (_sidebarMode == SidebarMode.Joined)
        {
            _sidebarTitle.Text = "Salas (doble clic para activar)";
            var items = new List<string>();
            if (_visitedRooms.Contains("global"))
            {
                items.Add("global");
            }

            items.AddRange(_visitedRooms.Where(r => !string.Equals(r, "global", StringComparison.OrdinalIgnoreCase))
                .OrderBy(r => r, StringComparer.OrdinalIgnoreCase));

            foreach (var room in items)
            {
                var prefix = string.Equals(room, _currentRoom, StringComparison.OrdinalIgnoreCase) ? "• " : "  ";
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
                foreach (var (name, empty) in _publicRoomsCache.OrderBy(r => r.Name, StringComparer.OrdinalIgnoreCase))
                {
                    _roomsListBox.Items.Add(empty ? $"{name} (vacía)" : name);
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
        if (_roomsListBox.SelectedItem is not string text)
        {
            return;
        }

        text = text.Trim();
        if (_sidebarMode == SidebarMode.Joined)
        {
            var room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2) : text;
            SwitchToRoom(room);
        }
        else
        {
            if (text.Equals("(no hay salas públicas)", StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            var room = RemoveVacantTag(text).Trim();
            JoinRoom(room);
        }
    }

    private void LeaveSelectedRoom()
    {
        if (_roomsListBox.SelectedItem is not string text)
        {
            return;
        }

        text = text.Trim();
        var room = text.StartsWith("• ") || text.StartsWith("  ") ? text.Substring(2) : text;
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
        var path = HistoryManager.HistoryPath(room, _serverKey);
        var (lines, startIndex) = HistoryManager.TailLines(path, LoadChunk);
        _historyIndex[room] = new RoomHistoryState { StartIndex = startIndex };
        _chatArea.ReadOnly = false;
        _chatArea.Clear();
        foreach (var line in lines)
        {
            _chatArea.AppendText(line + Environment.NewLine);
        }
        _chatArea.ReadOnly = true;
        _chatArea.SelectionStart = _chatArea.TextLength;
        _chatArea.ScrollToCaret();
    }

    private void LoadMoreHistoryChunk()
    {
        var room = _currentRoom;
        if (!_historyIndex.TryGetValue(room, out var state))
        {
            return;
        }

        var startIndex = state.StartIndex;
        if (startIndex == 0)
        {
            return;
        }

        var path = HistoryManager.HistoryPath(room, _serverKey);
        var (lines, newStart) = HistoryManager.HeadChunk(path, startIndex, LoadChunk);
        if (lines.Count == 0)
        {
            return;
        }

        var builder = new StringBuilder();
        for (var i = 0; i < lines.Count; i++)
        {
            builder.Append(lines[i]);
            builder.Append(Environment.NewLine);
        }

        var textToInsert = builder.ToString();

        _chatArea.ReadOnly = false;
        _chatArea.SelectionStart = 0;
        _chatArea.SelectionLength = 0;
        _chatArea.SelectedText = textToInsert;
        _chatArea.SelectionStart = textToInsert.Length;
        _chatArea.ScrollToCaret();
        _chatArea.ReadOnly = true;

        state.StartIndex = newStart;
    }

    private void AppendLocal(string text, string? room = null)
    {
        var targetRoom = room ?? _currentRoom;
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

    private static string NowTs() => DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss");

    private void DisconnectUi()
    {
        CloseConnection();
        _connectButton.Enabled = true;
        _sendButton.Enabled = false;
    }

    private void CloseConnection()
    {
        _running = false;
        try
        {
            _reader?.Dispose();
        }
        catch
        {
            // ignore
        }
        finally
        {
            _reader = null;
        }

        try
        {
            _writer?.Dispose();
        }
        catch
        {
            // ignore
        }
        finally
        {
            _writer = null;
        }

        try
        {
            _client?.Close();
        }
        catch
        {
            // ignore
        }
        finally
        {
            _client = null;
        }
    }

    private void OnFormClosing(object? sender, FormClosingEventArgs e)
    {
        _running = false;
        try
        {
            _writer?.WriteLine("/quitar");
        }
        catch
        {
            // ignore
        }
        CloseConnection();
    }

    private sealed class RoomHistoryState
    {
        public int StartIndex { get; set; }
    }

    private enum SidebarMode
    {
        Joined,
        PublicList
    }
}
