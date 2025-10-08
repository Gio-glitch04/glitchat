using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ClientC;

internal sealed class ChatRichTextBox : RichTextBox
{
    private const int WmVScroll = 0x115;
    private const int WmMouseWheel = 0x20A;
    private const int EmGetFirstVisibleLine = 0xCE;

    public event EventHandler? ScrolledToTop;

    protected override void WndProc(ref Message m)
    {
        base.WndProc(ref m);

        if (m.Msg == WmVScroll || m.Msg == WmMouseWheel)
        {
            CheckTop();
        }
    }

    private void CheckTop()
    {
        var firstVisible = SendMessage(Handle, EmGetFirstVisibleLine, IntPtr.Zero, IntPtr.Zero);
        if (firstVisible == IntPtr.Zero)
        {
            ScrolledToTop?.Invoke(this, EventArgs.Empty);
        }
    }

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
}
