using System;
using System.Drawing;
using System.Windows.Forms;

namespace ClientC;

internal static class PromptDialog
{
    public static string? ShowDialog(IWin32Window owner, string title, string message, bool password = false)
    {
        using var form = new Form
        {
            Text = title,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            StartPosition = FormStartPosition.CenterParent,
            MinimizeBox = false,
            MaximizeBox = false,
            ClientSize = new Size(320, 140)
        };

        var label = new Label { Text = message, AutoSize = false, Bounds = new Rectangle(10, 10, 300, 40) };
        var textBox = new TextBox { Bounds = new Rectangle(10, 60, 300, 23) };
        if (password)
        {
            textBox.UseSystemPasswordChar = true;
        }

        var okButton = new Button { Text = "Aceptar", DialogResult = DialogResult.OK, Bounds = new Rectangle(140, 100, 80, 25) };
        var cancelButton = new Button { Text = "Cancelar", DialogResult = DialogResult.Cancel, Bounds = new Rectangle(230, 100, 80, 25) };

        form.Controls.AddRange(new Control[] { label, textBox, okButton, cancelButton });
        form.AcceptButton = okButton;
        form.CancelButton = cancelButton;

        var result = form.ShowDialog(owner);
        return result == DialogResult.OK ? textBox.Text : null;
    }
}
