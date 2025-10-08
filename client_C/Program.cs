using System;
using System.Windows.Forms;

namespace ClientC
{
    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            HistoryManager.EnsureHistoryDirectory();
            Application.Run(new ChatClientForm());
        }
    }
}
