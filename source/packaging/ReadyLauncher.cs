using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("MediaPress")]
[assembly: AssemblyDescription("MediaPress offline portable launcher — By Maher Bakran")]
[assembly: AssemblyCompany("Maher Bakran")]
[assembly: AssemblyProduct("MediaPress")]
[assembly: AssemblyVersion("2.1.0.0")]
[assembly: System.Runtime.Versioning.TargetFramework(".NETFramework,Version=v4.8")]

[DataContract] public sealed class PackagePart {
    [DataMember] public string Name;
    [DataMember] public long Size;
    [DataMember] public string Sha256;
}
[DataContract] public sealed class CriticalFile {
    [DataMember] public string Path;
    [DataMember] public long Size;
}
[DataContract] public sealed class PackageManifest {
    [DataMember] public string Version;
    [DataMember] public string ArchiveRoot;
    [DataMember] public string ArchiveSha256;
    [DataMember] public long UncompressedBytes;
    [DataMember] public PackagePart[] Parts;
    [DataMember] public CriticalFile[] CriticalFiles;
}

// A seekable view over small package files; no combined ZIP or large memory buffer.
public sealed class PartStream : Stream {
    readonly List<FileStream> files = new List<FileStream>();
    readonly List<long> starts = new List<long>();
    long length, position;
    public PartStream(string directory, PackagePart[] parts, Action<int, string> progress, CancellationToken cancel) {
        try {
            if (parts == null || parts.Length == 0 || parts.Length > 64) throw new InvalidDataException("ملفات الحزمة غير مكتملة.");
            long verified = 0, total = parts.Sum(p => p.Size);
            foreach (PackagePart part in parts) {
                cancel.ThrowIfCancellationRequested();
                if (String.IsNullOrEmpty(part.Name) || Path.GetFileName(part.Name) != part.Name || part.Size <= 0)
                    throw new InvalidDataException("اسم غير صالح ضمن ملفات الحزمة.");
                string path = Path.Combine(directory, part.Name);
                if (!File.Exists(path)) throw new FileNotFoundException("نزّل المجلد كاملاً؛ الملف الناقص: " + part.Name);
                FileStream file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536);
                files.Add(file); starts.Add(length);
                if (file.Length != part.Size) throw new InvalidDataException("أعد تنزيل الملف غير المكتمل: " + part.Name);
                using (SHA256 hash = SHA256.Create()) {
                    byte[] buffer = new byte[65536]; int read;
                    while ((read = file.Read(buffer, 0, buffer.Length)) != 0) {
                        cancel.ThrowIfCancellationRequested();
                        hash.TransformBlock(buffer, 0, read, null, 0);
                        verified += read;
                        if (progress != null) progress((int)(15 * verified / total), "التحقق من ملفات التشغيل…");
                    }
                    hash.TransformFinalBlock(new byte[0], 0, 0);
                    if (!String.Equals(RuntimePackage.Hex(hash.Hash), part.Sha256, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("أعد تنزيل الملف غير المكتمل: " + part.Name);
                }
                file.Position = 0; length += file.Length;
            }
        } catch { Dispose(); throw; }
    }
    public override bool CanRead { get { return true; } }
    public override bool CanSeek { get { return true; } }
    public override bool CanWrite { get { return false; } }
    public override long Length { get { return length; } }
    public override long Position { get { return position; } set { Seek(value, SeekOrigin.Begin); } }
    public override int Read(byte[] buffer, int offset, int count) {
        if (buffer == null) throw new ArgumentNullException("buffer");
        if (offset < 0 || count < 0 || offset > buffer.Length - count) throw new ArgumentOutOfRangeException();
        int result = 0;
        while (count > 0 && position < length) {
            int index = files.Count - 1;
            while (index > 0 && starts[index] > position) index--;
            FileStream file = files[index]; file.Position = position - starts[index];
            int amount = (int)Math.Min((long)count, file.Length - file.Position);
            int read = file.Read(buffer, offset, amount);
            if (read == 0) throw new EndOfStreamException();
            position += read; offset += read; count -= read; result += read;
        }
        return result;
    }
    public override long Seek(long offset, SeekOrigin origin) {
        long next = origin == SeekOrigin.Begin ? offset : origin == SeekOrigin.Current ? checked(position + offset) : origin == SeekOrigin.End ? checked(length + offset) : -1;
        if (next < 0 || next > length) throw new IOException("Invalid package offset.");
        return position = next;
    }
    public override void Flush() { }
    public override void SetLength(long value) { throw new NotSupportedException(); }
    public override void Write(byte[] buffer, int offset, int count) { throw new NotSupportedException(); }
    protected override void Dispose(bool disposing) { if (disposing) foreach (FileStream file in files) file.Dispose(); base.Dispose(disposing); }
}

public static class RuntimePackage {
    public static string Hex(byte[] bytes) { return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant(); }
    public static PackageManifest Load(string basePath, string expectedHash) {
        string path = Path.Combine(basePath, "_internal", "runtime.json");
        if (!File.Exists(path)) throw new FileNotFoundException("خلي مجلد _internal بجانب MediaPress.exe، وانسخ مجلد البرنامج كاملاً.");
        if (new FileInfo(path).Length > 65536) throw new InvalidDataException("بيانات الحزمة غير صالحة.");
        byte[] raw = File.ReadAllBytes(path);
        using (SHA256 hash = SHA256.Create()) {
            if (!String.Equals(Hex(hash.ComputeHash(raw)), expectedHash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("ملفات الحزمة من إصدارات مختلفة. أعد تنزيل المجلد كاملاً.");
        }
        PackageManifest result;
        using (MemoryStream stream = new MemoryStream(raw))
            result = (PackageManifest)new DataContractJsonSerializer(typeof(PackageManifest)).ReadObject(stream);
        if (result == null || String.IsNullOrEmpty(result.ArchiveRoot) || Path.GetFileName(result.ArchiveRoot) != result.ArchiveRoot ||
            result.ArchiveSha256 == null || result.ArchiveSha256.Length != 64 || !result.ArchiveSha256.All(Uri.IsHexDigit) ||
            result.UncompressedBytes <= 0 || result.CriticalFiles == null || result.CriticalFiles.Length == 0)
            throw new InvalidDataException("بيانات الحزمة غير صالحة.");
        return result;
    }
    public static string Inside(string root, string relative) {
        if (String.IsNullOrEmpty(relative) || relative.IndexOf(':') >= 0 || Path.IsPathRooted(relative)) throw new InvalidDataException("مسار غير صالح في الحزمة.");
        string prefix = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string full = Path.GetFullPath(Path.Combine(prefix, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("مسار خارج مجلد البرنامج.");
        return full;
    }
    static bool IsReady(string cache, string manifestHash, PackageManifest manifest) {
        string marker = Path.Combine(cache, ".ready");
        if (!File.Exists(marker) || File.ReadAllText(marker).Trim() != manifestHash) return false;
        foreach (CriticalFile file in manifest.CriticalFiles) {
            string path = Inside(cache, file.Path);
            if (!File.Exists(path) || new FileInfo(path).Length != file.Size) return false;
        }
        return true;
    }
    public static string Prepare(string basePath, string manifestHash, Action<int, string> progress, CancellationToken cancel) {
        basePath = Path.GetFullPath(basePath);
        PackageManifest manifest = Load(basePath, manifestHash);
        string runtime = Path.Combine(basePath, "_runtime");
        string cache = Path.Combine(runtime, manifest.ArchiveSha256.Substring(0, 16));
        string executable = Inside(cache, manifest.ArchiveRoot + "/MediaPress.exe");
        if (IsReady(cache, manifestHash, manifest)) return executable;
        Directory.CreateDirectory(runtime);
        string stage = Path.Combine(runtime, ".prepare-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stage);
        try {
            using (PartStream stream = new PartStream(Path.Combine(basePath, "_internal"), manifest.Parts, progress, cancel))
            using (ZipArchive zip = new ZipArchive(stream, ZipArchiveMode.Read, false)) {
                if (zip.Entries.Sum(e => e.Length) != manifest.UncompressedBytes) throw new InvalidDataException("حجم الحزمة غير صحيح.");
                long written = 0;
                byte[] buffer = new byte[65536];
                foreach (ZipArchiveEntry entry in zip.Entries) {
                    cancel.ThrowIfCancellationRequested();
                    string relative = entry.FullName.Replace('\\', '/');
                    if (!relative.StartsWith(manifest.ArchiveRoot + "/", StringComparison.Ordinal) || ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                        throw new InvalidDataException("محتوى غير صالح في الحزمة.");
                    string path = Inside(stage, relative);
                    if (relative.EndsWith("/")) { Directory.CreateDirectory(path); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(path));
                    using (Stream input = entry.Open())
                    using (FileStream output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536)) {
                        int read;
                        while ((read = input.Read(buffer, 0, buffer.Length)) != 0) {
                            cancel.ThrowIfCancellationRequested();
                            output.Write(buffer, 0, read); written += read;
                            if (progress != null) progress(15 + (int)(85 * written / manifest.UncompressedBytes), "تجهيز البرنامج على جهازك…");
                        }
                    }
                }
            }
            File.WriteAllText(Path.Combine(stage, ".ready"), manifestHash, Encoding.UTF8);
            if (!IsReady(stage, manifestHash, manifest)) throw new InvalidDataException("لم تكتمل ملفات التشغيل.");
            cancel.ThrowIfCancellationRequested();
            if (Directory.Exists(cache)) Directory.Move(cache, cache + "-previous-" + Guid.NewGuid().ToString("N"));
            Directory.Move(stage, cache);
            return executable;
        } finally {
            // This path is created above by this process; never clean another folder.
            string expected = Path.GetFullPath(runtime).TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar + ".prepare-";
            if (Path.GetFullPath(stage).StartsWith(expected, StringComparison.OrdinalIgnoreCase) && Directory.Exists(stage)) {
                try { Directory.Delete(stage, true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
            }
        }
    }
}

sealed class PrepareDialog : Form {
    readonly CancellationTokenSource cancel = new CancellationTokenSource();
    readonly Label status = new Label();
    readonly Panel track = new Panel();
    readonly Panel fill = new Panel();
    readonly Func<Action<int, string>, CancellationToken, string> prepare;
    bool finished;
    int shownPercent = -1;
    public string Executable;
    public Exception Failure;
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    public PrepareDialog(Func<Action<int, string>, CancellationToken, string> action) {
        prepare = action; Text = "MediaPress"; BackColor = Color.FromArgb(18, 30, 30); ForeColor = Color.White;
        Font = new Font("Segoe UI", 10); AutoScaleMode = AutoScaleMode.Dpi;
        ClientSize = new Size(460, 194); StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false; MinimizeBox = false;
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Label title = new Label { Text = "MediaPress", Font = new Font("Segoe UI", 20, FontStyle.Bold), Location = new Point(25, 17), AutoSize = true };
        Label by = new Label { Text = "By Maher Bakran", ForeColor = Color.FromArgb(166, 193, 185), Location = new Point(28, 58), AutoSize = true };
        status.Text = "تجهيز البرنامج لأول تشغيل…"; status.Bounds = new Rectangle(25, 93, 410, 28);
        status.TextAlign = ContentAlignment.MiddleRight; status.RightToLeft = RightToLeft.Yes;
        track.Bounds = new Rectangle(28, 131, 404, 5); track.BackColor = Color.FromArgb(50, 69, 66);
        fill.BackColor = Color.FromArgb(75, 215, 169); fill.Dock = DockStyle.Left; fill.Width = 0; track.Controls.Add(fill);
        Button stop = new Button { Text = "إلغاء", Bounds = new Rectangle(352, 151, 80, 28), FlatStyle = FlatStyle.Flat, BackColor = BackColor, ForeColor = ForeColor };
        stop.FlatAppearance.BorderColor = Color.FromArgb(90, 119, 110);
        stop.Click += delegate { cancel.Cancel(); stop.Enabled = false; status.Text = "جارٍ الإلغاء…"; };
        Controls.AddRange(new Control[] { title, by, status, track, stop });
        Shown += delegate {
            int dark = 1; try { DwmSetWindowAttribute(Handle, 20, ref dark, 4); } catch (DllNotFoundException) { }
            Task.Run(delegate {
                try { Executable = prepare(UpdateProgress, cancel.Token); }
                catch (Exception error) { Failure = error; }
                BeginInvoke((Action)delegate { finished = true; DialogResult = Failure == null ? DialogResult.OK : DialogResult.Cancel; Close(); });
            });
        };
        FormClosing += delegate(object sender, FormClosingEventArgs e) { if (!finished) { cancel.Cancel(); e.Cancel = true; status.Text = "جارٍ الإلغاء…"; } };
    }
    void UpdateProgress(int percent, string text) {
        if (percent == shownPercent || cancel.IsCancellationRequested) return;
        shownPercent = percent;
        BeginInvoke((Action)delegate { if (!IsDisposed && !cancel.IsCancellationRequested) { fill.Width = track.Width * percent / 100; status.Text = text + " " + percent + "%"; } });
    }
    protected override void Dispose(bool disposing) { if (disposing) cancel.Dispose(); base.Dispose(disposing); }
}

static class ReadyLauncher {
    const string ManifestHash = "@@MANIFEST_SHA@@";
    static string Quote(string value) {
        StringBuilder result = new StringBuilder("\""); int slashes = 0;
        foreach (char ch in value) {
            if (ch == '\\') { slashes++; continue; }
            if (ch == '"') { result.Append('\\', slashes * 2 + 1); result.Append('"'); }
            else { result.Append('\\', slashes); result.Append(ch); }
            slashes = 0;
        }
        result.Append('\\', slashes * 2); return result.Append('"').ToString();
    }
    [STAThread] static int Main(string[] args) {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        string basePath = AppDomain.CurrentDomain.BaseDirectory;
        bool quiet = args.Length > 0 && (args[0] == "--self-test" || args[0] == "--prepare-only");
        try {
            string lockName; using (SHA256 hash = SHA256.Create()) lockName = RuntimePackage.Hex(hash.ComputeHash(Encoding.UTF8.GetBytes(basePath.ToLowerInvariant()))).Substring(0, 24);
            string executable;
            using (Mutex mutex = new Mutex(false, "Local\\MediaPress-Prepare-" + lockName)) {
                bool owned; try { owned = mutex.WaitOne(0); } catch (AbandonedMutexException) { owned = true; }
                if (!owned) return 0;
                try {
                    Func<Action<int, string>, CancellationToken, string> action = (progress, cancel) => RuntimePackage.Prepare(basePath, ManifestHash, progress, cancel);
                    if (quiet) executable = action(null, CancellationToken.None);
                    else {
                        // A prepared package returns immediately without flashing a window.
                        PackageManifest manifest = RuntimePackage.Load(basePath, ManifestHash);
                        string marker = Path.Combine(basePath, "_runtime", manifest.ArchiveSha256.Substring(0, 16), ".ready");
                        if (File.Exists(marker)) executable = action(null, CancellationToken.None);
                        else {
                            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
                            using (PrepareDialog dialog = new PrepareDialog(action)) {
                                dialog.ShowDialog();
                                if (dialog.Failure != null) throw dialog.Failure;
                                executable = dialog.Executable;
                            }
                        }
                    }
                } finally { mutex.ReleaseMutex(); }
            }
            if (args.Length > 0 && args[0] == "--prepare-only") return 0;
            ProcessStartInfo info = new ProcessStartInfo(executable) { WorkingDirectory = Path.GetDirectoryName(executable), UseShellExecute = false, Arguments = String.Join(" ", args.Select(Quote).ToArray()), CreateNoWindow = quiet };
            if (quiet) info.WindowStyle = ProcessWindowStyle.Hidden;
            using (Process process = Process.Start(info)) { if (quiet) { process.WaitForExit(); return process.ExitCode; } }
            return 0;
        } catch (OperationCanceledException) { return 0; }
        catch (Exception error) {
            try { File.WriteAllText(Path.Combine(basePath, "MediaPress-launch.log"), error.ToString(), Encoding.UTF8); } catch (IOException) { } catch (UnauthorizedAccessException) { }
            if (!quiet) MessageBox.Show("ما اكتمل تشغيل MediaPress.\n\n" + error.Message + "\n\nراجع اقرأني.txt أو نزّل المجلد كاملاً من جديد.", "MediaPress", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
