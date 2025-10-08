using System;
using System.Windows.Forms;

namespace ChatClient
{
    internal static class Extensions
    {
        public static void SafeInvoke(this Control control, Action action)
        {
            if (control.InvokeRequired)
            {
                control.BeginInvoke(action);
            }
            else
            {
                action();
            }
        }
    }
}
