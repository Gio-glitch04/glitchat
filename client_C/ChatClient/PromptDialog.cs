using System;
using System.Windows.Forms;

namespace ChatClient
{
    public partial class PromptDialog : Form
    {
        private PromptDialog(string title, string message, string defaultValue, bool mask)
        {
            InitializeComponent();
            Text = title;
            messageLabel.Text = message;
            inputTextBox.Text = defaultValue ?? string.Empty;
            if (mask)
            {
                inputTextBox.UseSystemPasswordChar = true;
            }
        }

        private void OkButton_Click(object sender, EventArgs e)
        {
            DialogResult = DialogResult.OK;
            Close();
        }

        public static string Show(IWin32Window owner, string title, string message, string defaultValue = "", bool mask = false)
        {
            using (var dialog = new PromptDialog(title, message, defaultValue, mask))
            {
                return dialog.ShowDialog(owner) == DialogResult.OK ? dialog.inputTextBox.Text : null;
            }
        }
    }
}
