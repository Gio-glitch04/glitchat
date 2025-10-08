namespace ChatClient
{
    partial class MainForm
    {
        private System.ComponentModel.IContainer components = null;
        private System.Windows.Forms.TextBox serverTextBox;
        private System.Windows.Forms.TextBox portTextBox;
        private System.Windows.Forms.TextBox userTextBox;
        private System.Windows.Forms.Button connectButton;
        private System.Windows.Forms.ComboBox serversComboBox;
        private System.Windows.Forms.Button saveServerButton;
        private System.Windows.Forms.ListBox roomsListBox;
        private System.Windows.Forms.Label sidebarTitleLabel;
        private System.Windows.Forms.Button joinedRoomsButton;
        private System.Windows.Forms.Button publicRoomsButton;
        private System.Windows.Forms.Button createJoinButton;
        private System.Windows.Forms.Label activeRoomLabel;
        private System.Windows.Forms.RichTextBox chatRichTextBox;
        private System.Windows.Forms.TextBox messageTextBox;
        private System.Windows.Forms.Button sendButton;
        private System.Windows.Forms.ContextMenuStrip roomsContextMenu;
        private System.Windows.Forms.ToolStripMenuItem leaveRoomMenuItem;
        private System.Windows.Forms.Label labelServer;
        private System.Windows.Forms.Label labelPort;
        private System.Windows.Forms.Label labelUser;
        private System.Windows.Forms.Label labelRecent;
        private System.Windows.Forms.Panel sidebarPanel;
        private System.Windows.Forms.Panel mainPanel;
        private System.Windows.Forms.Panel topPanel;
        private System.Windows.Forms.Panel bottomPanel;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.components = new System.ComponentModel.Container();
            this.serverTextBox = new System.Windows.Forms.TextBox();
            this.portTextBox = new System.Windows.Forms.TextBox();
            this.userTextBox = new System.Windows.Forms.TextBox();
            this.connectButton = new System.Windows.Forms.Button();
            this.serversComboBox = new System.Windows.Forms.ComboBox();
            this.saveServerButton = new System.Windows.Forms.Button();
            this.roomsListBox = new System.Windows.Forms.ListBox();
            this.roomsContextMenu = new System.Windows.Forms.ContextMenuStrip(this.components);
            this.leaveRoomMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.sidebarTitleLabel = new System.Windows.Forms.Label();
            this.joinedRoomsButton = new System.Windows.Forms.Button();
            this.publicRoomsButton = new System.Windows.Forms.Button();
            this.createJoinButton = new System.Windows.Forms.Button();
            this.activeRoomLabel = new System.Windows.Forms.Label();
            this.chatRichTextBox = new System.Windows.Forms.RichTextBox();
            this.messageTextBox = new System.Windows.Forms.TextBox();
            this.sendButton = new System.Windows.Forms.Button();
            this.labelServer = new System.Windows.Forms.Label();
            this.labelPort = new System.Windows.Forms.Label();
            this.labelUser = new System.Windows.Forms.Label();
            this.labelRecent = new System.Windows.Forms.Label();
            this.sidebarPanel = new System.Windows.Forms.Panel();
            this.mainPanel = new System.Windows.Forms.Panel();
            this.topPanel = new System.Windows.Forms.Panel();
            this.bottomPanel = new System.Windows.Forms.Panel();
            this.roomsContextMenu.SuspendLayout();
            this.sidebarPanel.SuspendLayout();
            this.mainPanel.SuspendLayout();
            this.topPanel.SuspendLayout();
            this.bottomPanel.SuspendLayout();
            this.SuspendLayout();
            // 
            // serverTextBox
            // 
            this.serverTextBox.Location = new System.Drawing.Point(64, 16);
            this.serverTextBox.Name = "serverTextBox";
            this.serverTextBox.Size = new System.Drawing.Size(125, 20);
            this.serverTextBox.TabIndex = 1;
            // 
            // portTextBox
            // 
            this.portTextBox.Location = new System.Drawing.Point(248, 16);
            this.portTextBox.Name = "portTextBox";
            this.portTextBox.Size = new System.Drawing.Size(60, 20);
            this.portTextBox.TabIndex = 3;
            // 
            // userTextBox
            // 
            this.userTextBox.Location = new System.Drawing.Point(360, 16);
            this.userTextBox.Name = "userTextBox";
            this.userTextBox.Size = new System.Drawing.Size(140, 20);
            this.userTextBox.TabIndex = 5;
            // 
            // connectButton
            // 
            this.connectButton.Location = new System.Drawing.Point(512, 16);
            this.connectButton.Name = "connectButton";
            this.connectButton.Size = new System.Drawing.Size(86, 23);
            this.connectButton.TabIndex = 6;
            this.connectButton.Text = "Conectar";
            this.connectButton.UseVisualStyleBackColor = true;
            this.connectButton.Click += new System.EventHandler(this.ConnectButton_Click);
            // 
            // serversComboBox
            // 
            this.serversComboBox.DropDownStyle = System.Windows.Forms.ComboBoxStyle.DropDownList;
            this.serversComboBox.FormattingEnabled = true;
            this.serversComboBox.Location = new System.Drawing.Point(672, 16);
            this.serversComboBox.Name = "serversComboBox";
            this.serversComboBox.Size = new System.Drawing.Size(160, 21);
            this.serversComboBox.TabIndex = 9;
            this.serversComboBox.SelectedIndexChanged += new System.EventHandler(this.ServersComboBox_SelectedIndexChanged);
            // 
            // saveServerButton
            // 
            this.saveServerButton.Location = new System.Drawing.Point(848, 16);
            this.saveServerButton.Name = "saveServerButton";
            this.saveServerButton.Size = new System.Drawing.Size(126, 23);
            this.saveServerButton.TabIndex = 10;
            this.saveServerButton.Text = "Guardar servidor...";
            this.saveServerButton.UseVisualStyleBackColor = true;
            this.saveServerButton.Click += new System.EventHandler(this.SaveServerButton_Click);
            // 
            // roomsListBox
            // 
            this.roomsListBox.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom) 
            | System.Windows.Forms.AnchorStyles.Left)));
            this.roomsListBox.ContextMenuStrip = this.roomsContextMenu;
            this.roomsListBox.DrawMode = System.Windows.Forms.DrawMode.OwnerDrawFixed;
            this.roomsListBox.FormattingEnabled = true;
            this.roomsListBox.IntegralHeight = false;
            this.roomsListBox.Location = new System.Drawing.Point(15, 44);
            this.roomsListBox.Name = "roomsListBox";
            this.roomsListBox.Size = new System.Drawing.Size(210, 365);
            this.roomsListBox.TabIndex = 2;
            this.roomsListBox.DrawItem += new System.Windows.Forms.DrawItemEventHandler(this.RoomsListBox_DrawItem);
            this.roomsListBox.DoubleClick += new System.EventHandler(this.RoomsListBox_DoubleClick);
            this.roomsListBox.MouseDown += new System.Windows.Forms.MouseEventHandler(this.RoomsListBox_MouseDown);
            // 
            // roomsContextMenu
            // 
            this.roomsContextMenu.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.leaveRoomMenuItem});
            this.roomsContextMenu.Name = "roomsContextMenu";
            this.roomsContextMenu.Size = new System.Drawing.Size(148, 26);
            this.roomsContextMenu.Opening += new System.ComponentModel.CancelEventHandler(this.RoomsContextMenu_Opening);
            // 
            // leaveRoomMenuItem
            // 
            this.leaveRoomMenuItem.Name = "leaveRoomMenuItem";
            this.leaveRoomMenuItem.Size = new System.Drawing.Size(147, 22);
            this.leaveRoomMenuItem.Text = "Salir de la sala";
            this.leaveRoomMenuItem.Click += new System.EventHandler(this.LeaveRoomMenuItem_Click);
            // 
            // sidebarTitleLabel
            // 
            this.sidebarTitleLabel.AutoSize = true;
            this.sidebarTitleLabel.Location = new System.Drawing.Point(12, 20);
            this.sidebarTitleLabel.Name = "sidebarTitleLabel";
            this.sidebarTitleLabel.Size = new System.Drawing.Size(146, 13);
            this.sidebarTitleLabel.TabIndex = 1;
            this.sidebarTitleLabel.Text = "Salas (doble clic para activar)";
            // 
            // joinedRoomsButton
            // 
            this.joinedRoomsButton.Location = new System.Drawing.Point(15, 418);
            this.joinedRoomsButton.Name = "joinedRoomsButton";
            this.joinedRoomsButton.Size = new System.Drawing.Size(102, 28);
            this.joinedRoomsButton.TabIndex = 3;
            this.joinedRoomsButton.Text = "Mis salas";
            this.joinedRoomsButton.UseVisualStyleBackColor = true;
            this.joinedRoomsButton.Click += new System.EventHandler(this.JoinedRoomsButton_Click);
            // 
            // publicRoomsButton
            // 
            this.publicRoomsButton.Location = new System.Drawing.Point(123, 418);
            this.publicRoomsButton.Name = "publicRoomsButton";
            this.publicRoomsButton.Size = new System.Drawing.Size(102, 28);
            this.publicRoomsButton.TabIndex = 4;
            this.publicRoomsButton.Text = "Listar públicas";
            this.publicRoomsButton.UseVisualStyleBackColor = true;
            this.publicRoomsButton.Click += new System.EventHandler(this.PublicRoomsButton_Click);
            // 
            // createJoinButton
            // 
            this.createJoinButton.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.createJoinButton.Location = new System.Drawing.Point(15, 453);
            this.createJoinButton.Name = "createJoinButton";
            this.createJoinButton.Size = new System.Drawing.Size(210, 30);
            this.createJoinButton.TabIndex = 5;
            this.createJoinButton.Text = "Crear / Unirse a sala";
            this.createJoinButton.UseVisualStyleBackColor = true;
            this.createJoinButton.Click += new System.EventHandler(this.CreateJoinButton_Click);
            // 
            // activeRoomLabel
            // 
            this.activeRoomLabel.AutoSize = true;
            this.activeRoomLabel.Font = new System.Drawing.Font("Microsoft Sans Serif", 9.75F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.activeRoomLabel.Location = new System.Drawing.Point(12, 9);
            this.activeRoomLabel.Name = "activeRoomLabel";
            this.activeRoomLabel.Size = new System.Drawing.Size(137, 16);
            this.activeRoomLabel.TabIndex = 0;
            this.activeRoomLabel.Text = "Sala activa: global";
            // 
            // chatRichTextBox
            // 
            this.chatRichTextBox.Anchor = ((System.Windows.Forms.AnchorStyles)((((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom) 
            | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.chatRichTextBox.Location = new System.Drawing.Point(15, 35);
            this.chatRichTextBox.Name = "chatRichTextBox";
            this.chatRichTextBox.ReadOnly = true;
            this.chatRichTextBox.Size = new System.Drawing.Size(724, 410);
            this.chatRichTextBox.TabIndex = 1;
            this.chatRichTextBox.Text = "";
            this.chatRichTextBox.VScroll += new System.EventHandler(this.ChatRichTextBox_VScroll);
            // 
            // messageTextBox
            // 
            this.messageTextBox.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.messageTextBox.Location = new System.Drawing.Point(15, 10);
            this.messageTextBox.Name = "messageTextBox";
            this.messageTextBox.Size = new System.Drawing.Size(634, 20);
            this.messageTextBox.TabIndex = 0;
            this.messageTextBox.KeyDown += new System.Windows.Forms.KeyEventHandler(this.MessageTextBox_KeyDown);
            // 
            // sendButton
            // 
            this.sendButton.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.sendButton.Enabled = false;
            this.sendButton.Location = new System.Drawing.Point(655, 8);
            this.sendButton.Name = "sendButton";
            this.sendButton.Size = new System.Drawing.Size(84, 23);
            this.sendButton.TabIndex = 1;
            this.sendButton.Text = "Enviar";
            this.sendButton.UseVisualStyleBackColor = true;
            this.sendButton.Click += new System.EventHandler(this.SendButton_Click);
            // 
            // labelServer
            // 
            this.labelServer.AutoSize = true;
            this.labelServer.Location = new System.Drawing.Point(8, 16);
            this.labelServer.Name = "labelServer";
            this.labelServer.Size = new System.Drawing.Size(49, 13);
            this.labelServer.TabIndex = 0;
            this.labelServer.Text = "Servidor:";
            // 
            // labelPort
            // 
            this.labelPort.AutoSize = true;
            this.labelPort.Location = new System.Drawing.Point(200, 16);
            this.labelPort.Name = "labelPort";
            this.labelPort.Size = new System.Drawing.Size(41, 13);
            this.labelPort.TabIndex = 2;
            this.labelPort.Text = "Puerto:";
            // 
            // labelUser
            // 
            this.labelUser.AutoSize = true;
            this.labelUser.Location = new System.Drawing.Point(312, 16);
            this.labelUser.Name = "labelUser";
            this.labelUser.Size = new System.Drawing.Size(46, 13);
            this.labelUser.TabIndex = 4;
            this.labelUser.Text = "Usuario:";
            // 
            // labelRecent
            // 
            this.labelRecent.AutoSize = true;
            this.labelRecent.Location = new System.Drawing.Point(608, 16);
            this.labelRecent.Name = "labelRecent";
            this.labelRecent.Size = new System.Drawing.Size(58, 13);
            this.labelRecent.TabIndex = 8;
            this.labelRecent.Text = "Recientes:";
            // 
            // sidebarPanel
            // 
            this.sidebarPanel.Controls.Add(this.sidebarTitleLabel);
            this.sidebarPanel.Controls.Add(this.roomsListBox);
            this.sidebarPanel.Controls.Add(this.joinedRoomsButton);
            this.sidebarPanel.Controls.Add(this.publicRoomsButton);
            this.sidebarPanel.Controls.Add(this.createJoinButton);
            this.sidebarPanel.Dock = System.Windows.Forms.DockStyle.Left;
            this.sidebarPanel.Location = new System.Drawing.Point(0, 50);
            this.sidebarPanel.Name = "sidebarPanel";
            this.sidebarPanel.Size = new System.Drawing.Size(240, 501);
            this.sidebarPanel.TabIndex = 1;
            // 
            // mainPanel
            // 
            this.mainPanel.Controls.Add(this.chatRichTextBox);
            this.mainPanel.Controls.Add(this.activeRoomLabel);
            this.mainPanel.Dock = System.Windows.Forms.DockStyle.Fill;
            this.mainPanel.Location = new System.Drawing.Point(240, 50);
            this.mainPanel.Name = "mainPanel";
            this.mainPanel.Size = new System.Drawing.Size(754, 441);
            this.mainPanel.TabIndex = 2;
            // 
            // topPanel
            // 
            this.topPanel.Controls.Add(this.labelServer);
            this.topPanel.Controls.Add(this.serverTextBox);
            this.topPanel.Controls.Add(this.labelPort);
            this.topPanel.Controls.Add(this.portTextBox);
            this.topPanel.Controls.Add(this.labelUser);
            this.topPanel.Controls.Add(this.userTextBox);
            this.topPanel.Controls.Add(this.connectButton);
            this.topPanel.Controls.Add(this.labelRecent);
            this.topPanel.Controls.Add(this.serversComboBox);
            this.topPanel.Controls.Add(this.saveServerButton);
            this.topPanel.Dock = System.Windows.Forms.DockStyle.Top;
            this.topPanel.Location = new System.Drawing.Point(0, 0);
            this.topPanel.Name = "topPanel";
            this.topPanel.Size = new System.Drawing.Size(994, 50);
            this.topPanel.TabIndex = 0;
            // 
            // bottomPanel
            // 
            this.bottomPanel.Controls.Add(this.messageTextBox);
            this.bottomPanel.Controls.Add(this.sendButton);
            this.bottomPanel.Dock = System.Windows.Forms.DockStyle.Bottom;
            this.bottomPanel.Location = new System.Drawing.Point(240, 491);
            this.bottomPanel.Name = "bottomPanel";
            this.bottomPanel.Size = new System.Drawing.Size(754, 60);
            this.bottomPanel.TabIndex = 3;
            // 
            // MainForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(994, 551);
            this.Controls.Add(this.mainPanel);
            this.Controls.Add(this.bottomPanel);
            this.Controls.Add(this.sidebarPanel);
            this.Controls.Add(this.topPanel);
            this.MinimumSize = new System.Drawing.Size(960, 590);
            this.Name = "MainForm";
            this.Text = "Chat - Cliente (WinForms)";
            this.FormClosing += new System.Windows.Forms.FormClosingEventHandler(this.MainForm_FormClosing);
            this.roomsContextMenu.ResumeLayout(false);
            this.sidebarPanel.ResumeLayout(false);
            this.sidebarPanel.PerformLayout();
            this.mainPanel.ResumeLayout(false);
            this.mainPanel.PerformLayout();
            this.topPanel.ResumeLayout(false);
            this.topPanel.PerformLayout();
            this.bottomPanel.ResumeLayout(false);
            this.bottomPanel.PerformLayout();
            this.ResumeLayout(false);

        }
    }
}
