using System;
using System.Drawing;
using System.Windows.Forms;

namespace ClientC;

internal sealed class CreateJoinForm : Form
{
    private readonly TextBox _roomEntry;
    private readonly TextBox _passwordEntry;

    public string? RoomName => _roomEntry.Text;
    public string? Password => _passwordEntry.Text;

    public CreateJoinForm()
    {
        Text = "Crear / Unirse a sala";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MinimizeBox = false;
        MaximizeBox = false;
        ClientSize = new Size(320, 160);

        var nameLabel = new Label { Text = "Nombre de la sala:", AutoSize = true, Location = new Point(10, 20) };
        Controls.Add(nameLabel);

        _roomEntry = new TextBox { Location = new Point(150, 17), Width = 150 };
        Controls.Add(_roomEntry);

        var passwordLabel = new Label { Text = "Contraseña (opcional):", AutoSize = true, Location = new Point(10, 60) };
        Controls.Add(passwordLabel);

        _passwordEntry = new TextBox { Location = new Point(150, 57), Width = 150, UseSystemPasswordChar = true };
        Controls.Add(_passwordEntry);

        var okButton = new Button { Text = "Aceptar", DialogResult = DialogResult.OK, Location = new Point(120, 110), Width = 80 };
        var cancelButton = new Button { Text = "Cancelar", DialogResult = DialogResult.Cancel, Location = new Point(210, 110), Width = 80 };
        Controls.Add(okButton);
        Controls.Add(cancelButton);

        AcceptButton = okButton;
        CancelButton = cancelButton;
    }
}
