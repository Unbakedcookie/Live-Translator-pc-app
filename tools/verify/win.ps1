<#
  T004 - Desktop verification helper for Tier B checks (rule 7).
  No third-party dependencies: uses user32/dwmapi via Add-Type and System.Drawing.
  All coordinates are PHYSICAL screen pixels (process is made DPI-aware).

  Actions:
    list   [-Title <substr>]                     Visible top-level windows: hwnd, pid, title, rect, topmost, alpha, clickthrough
    shot   -Out <png> [-Title <substr>] [-MaxWidth <px>]
                                                 Screenshot of the whole virtual desktop, or of the first window matching -Title.
                                                 Prints origin and scale so image pixels map back to screen: screen = origin + px / scale
    focus  -Title <substr>                       Bring matching window to foreground
    move   -X <x> -Y <y>                         Move cursor
    click  -X <x> -Y <y> [-Button left|right] [-Double]
    drag   -X <x> -Y <y> -X2 <x> -Y2 <y> [-Steps <n>]
    scroll -X <x> -Y <y> -Delta <notches>        Positive = up
    keys   -Keys <SendKeys string>               e.g. "^+p" for Ctrl+Shift+P, "{ESC}"

  Usage (from Git Bash):
    powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify/win.ps1 -Action list -Title "Live Translator"
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('list', 'shot', 'focus', 'move', 'click', 'drag', 'scroll', 'keys')]
    [string]$Action,
    [string]$Title = '',
    [string]$Out = '',
    [int]$MaxWidth = 0,
    [int]$X = 0,
    [int]$Y = 0,
    [int]$X2 = 0,
    [int]$Y2 = 0,
    [int]$Steps = 20,
    [int]$Delta = 1,
    [ValidateSet('left', 'right')]
    [string]$Button = 'left',
    [switch]$Double,
    [string]$Keys = ''
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName System.Windows.Forms

if (-not ('VerifyWin' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;

public static class VerifyWin {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr lParam);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int max);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT r);
    [DllImport("dwmapi.dll")] public static extern int DwmGetWindowAttribute(IntPtr hWnd, int attr, out RECT r, int size);
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")] public static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int index);
    [DllImport("user32.dll")] public static extern bool GetLayeredWindowAttributes(IntPtr hWnd, out uint key, out byte alpha, out uint flags);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, int dx, int dy, int data, UIntPtr extra);

    public const int GWL_EXSTYLE = -20;
    public const long WS_EX_TOPMOST = 0x8;
    public const long WS_EX_TRANSPARENT = 0x20;
    public const long WS_EX_LAYERED = 0x80000;
    public const uint LWA_ALPHA = 0x2;

    public static List<IntPtr> Visible() {
        var list = new List<IntPtr>();
        EnumWindows(delegate (IntPtr h, IntPtr p) { if (IsWindowVisible(h)) list.Add(h); return true; }, IntPtr.Zero);
        return list;
    }

    public static string Text(IntPtr h) {
        var sb = new StringBuilder(512);
        GetWindowText(h, sb, sb.Capacity);
        return sb.ToString();
    }

    // DWM extended frame bounds exclude the invisible resize border; fall back to GetWindowRect.
    public static RECT Bounds(IntPtr h) {
        RECT r;
        if (DwmGetWindowAttribute(h, 9, out r, Marshal.SizeOf(typeof(RECT))) != 0) GetWindowRect(h, out r);
        return r;
    }

    public static long ExStyle(IntPtr h) { return GetWindowLongPtr(h, GWL_EXSTYLE).ToInt64(); }

    // Returns 0-255 if the window uses layered alpha, -1 otherwise.
    public static int Alpha(IntPtr h) {
        uint key, flags; byte alpha;
        if ((ExStyle(h) & WS_EX_LAYERED) == 0) return -1;
        if (!GetLayeredWindowAttributes(h, out key, out alpha, out flags)) return -1;
        return (flags & LWA_ALPHA) != 0 ? alpha : -1;
    }

    public static uint Pid(IntPtr h) { uint pid; GetWindowThreadProcessId(h, out pid); return pid; }

    [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hWnd, IntPtr hdc);
    [DllImport("gdi32.dll")] public static extern bool BitBlt(IntPtr dst, int dx, int dy, int w, int h, IntPtr src, int sx, int sy, uint rop);

    // SRCCOPY | CAPTUREBLT so layered (translucent) windows are included.
    // System.Drawing's CopyFromScreen rejects the combined flag, hence raw GDI.
    public static void CaptureInto(IntPtr dstHdc, int x, int y, int w, int h) {
        IntPtr screen = GetDC(IntPtr.Zero);
        try { BitBlt(dstHdc, 0, 0, w, h, screen, x, y, 0x00CC0020 | 0x40000000); }
        finally { ReleaseDC(IntPtr.Zero, screen); }
    }
}
'@
}

[void][VerifyWin]::SetProcessDPIAware()

function Get-Windows([string]$filter) {
    foreach ($h in [VerifyWin]::Visible()) {
        $t = [VerifyWin]::Text($h)
        if ([string]::IsNullOrWhiteSpace($t)) { continue }
        if ($filter -and ($t -notlike "*$filter*")) { continue }
        $r = [VerifyWin]::Bounds($h)
        $ex = [VerifyWin]::ExStyle($h)
        [pscustomobject]@{
            Hwnd         = ('0x{0:X}' -f $h.ToInt64())
            Handle       = $h
            Pid          = [VerifyWin]::Pid($h)
            Title        = $t
            X            = $r.Left
            Y            = $r.Top
            W            = $r.Right - $r.Left
            H            = $r.Bottom - $r.Top
            Topmost      = [bool]($ex -band [VerifyWin]::WS_EX_TOPMOST)
            ClickThrough = [bool]($ex -band [VerifyWin]::WS_EX_TRANSPARENT)
            Alpha        = [VerifyWin]::Alpha($h)
        }
    }
}

function Get-FirstWindow([string]$filter) {
    $w = @(Get-Windows $filter) | Select-Object -First 1
    if (-not $w) { throw "No visible window with title containing '$filter'" }
    return $w
}

function Send-Mouse([uint32]$flags, [int]$data = 0) {
    [VerifyWin]::mouse_event($flags, 0, 0, $data, [UIntPtr]::Zero)
}

$LEFTDOWN = 0x2; $LEFTUP = 0x4; $RIGHTDOWN = 0x8; $RIGHTUP = 0x10; $WHEEL = 0x800

switch ($Action) {
    'list' {
        Get-Windows $Title | Select-Object Hwnd, Pid, Title, X, Y, W, H, Topmost, ClickThrough, Alpha | Format-Table -AutoSize | Out-String -Width 400
    }
    'shot' {
        if (-not $Out) { throw '-Out <path.png> is required for shot' }
        if ($Title) {
            $w = Get-FirstWindow $Title
            $rect = New-Object System.Drawing.Rectangle($w.X, $w.Y, $w.W, $w.H)
        } else {
            $rect = [System.Windows.Forms.SystemInformation]::VirtualScreen
        }
        $bmp = New-Object System.Drawing.Bitmap($rect.Width, $rect.Height)
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $hdc = $g.GetHdc()
        try { [VerifyWin]::CaptureInto($hdc, $rect.X, $rect.Y, $rect.Width, $rect.Height) }
        finally { $g.ReleaseHdc($hdc); $g.Dispose() }
        $scale = 1.0
        if ($MaxWidth -gt 0 -and $bmp.Width -gt $MaxWidth) {
            $scale = $MaxWidth / $bmp.Width
            $small = New-Object System.Drawing.Bitmap($bmp, [int]($bmp.Width * $scale), [int]($bmp.Height * $scale))
            $bmp.Dispose()
            $bmp = $small
        }
        $dir = Split-Path -Parent $Out
        if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
        $bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
        $bmp.Dispose()
        "saved=$Out origin=($($rect.X),$($rect.Y)) size=$($rect.Width)x$($rect.Height) scale=$([math]::Round($scale,4))  (screen = origin + px / scale)"
    }
    'focus' {
        $w = Get-FirstWindow $Title
        [void][VerifyWin]::SetForegroundWindow($w.Handle)
        "focused $($w.Hwnd) '$($w.Title)'"
    }
    'move' {
        [void][VerifyWin]::SetCursorPos($X, $Y)
        "cursor=($X,$Y)"
    }
    'click' {
        [void][VerifyWin]::SetCursorPos($X, $Y)
        Start-Sleep -Milliseconds 60
        $down = if ($Button -eq 'right') { $RIGHTDOWN } else { $LEFTDOWN }
        $up = if ($Button -eq 'right') { $RIGHTUP } else { $LEFTUP }
        $count = if ($Double) { 2 } else { 1 }
        for ($i = 0; $i -lt $count; $i++) {
            Send-Mouse $down; Start-Sleep -Milliseconds 40; Send-Mouse $up; Start-Sleep -Milliseconds 80
        }
        "$Button-click x$count at ($X,$Y)"
    }
    'drag' {
        [void][VerifyWin]::SetCursorPos($X, $Y)
        Start-Sleep -Milliseconds 80
        Send-Mouse $LEFTDOWN
        Start-Sleep -Milliseconds 80
        for ($i = 1; $i -le $Steps; $i++) {
            $cx = [int]($X + ($X2 - $X) * $i / $Steps)
            $cy = [int]($Y + ($Y2 - $Y) * $i / $Steps)
            [void][VerifyWin]::SetCursorPos($cx, $cy)
            Start-Sleep -Milliseconds 15
        }
        Start-Sleep -Milliseconds 80
        Send-Mouse $LEFTUP
        "dragged ($X,$Y) -> ($X2,$Y2) in $Steps steps"
    }
    'scroll' {
        [void][VerifyWin]::SetCursorPos($X, $Y)
        Start-Sleep -Milliseconds 60
        Send-Mouse $WHEEL ($Delta * 120)
        "scrolled $Delta notch(es) at ($X,$Y)"
    }
    'keys' {
        if (-not $Keys) { throw '-Keys is required for keys' }
        [System.Windows.Forms.SendKeys]::SendWait($Keys)
        "sent keys '$Keys'"
    }
}
