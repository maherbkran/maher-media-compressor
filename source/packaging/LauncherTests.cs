using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Runtime.Serialization.Json;
using System.Security.Cryptography;
using System.Threading;

static class LauncherTests {
    sealed class Fixture {
        public string Folder, Hash;
        public PackageManifest Manifest;
        public byte[] Archive;
    }
    static string root;
    static void Assert(bool value, string message) { if (!value) throw new Exception(message); }
    static void Reject<T>(Action action) where T : Exception {
        try { action(); } catch (T) { return; }
        throw new Exception("Expected " + typeof(T).Name);
    }
    static Fixture Make(string name, bool traversal) {
        string folder = Path.Combine(root, name + " مسار عربي");
        string partsFolder = Path.Combine(folder, "_internal"); Directory.CreateDirectory(partsFolder);
        byte[] data = new byte[120000]; new Random(123).NextBytes(data);
        byte[] exe = new byte[100]; new Random(321).NextBytes(exe);
        byte[] archive;
        using (MemoryStream memory = new MemoryStream()) {
            using (ZipArchive zip = new ZipArchive(memory, ZipArchiveMode.Create, true)) {
                using (Stream file = zip.CreateEntry("MediaPress-v2.1.0/MediaPress.exe").Open()) file.Write(exe, 0, exe.Length);
                using (Stream file = zip.CreateEntry("MediaPress-v2.1.0/data.bin").Open()) file.Write(data, 0, data.Length);
                if (traversal) using (Stream file = zip.CreateEntry("MediaPress-v2.1.0/../../outside.txt").Open()) file.WriteByte(1);
            }
            archive = memory.ToArray();
        }
        List<PackagePart> parts = new List<PackagePart>();
        for (int offset = 0; offset < archive.Length; offset += 8192) {
            byte[] bytes = archive.Skip(offset).Take(8192).ToArray();
            string partName = "part." + (parts.Count + 1).ToString("D3");
            File.WriteAllBytes(Path.Combine(partsFolder, partName), bytes);
            using (SHA256 sha = SHA256.Create()) parts.Add(new PackagePart { Name = partName, Size = bytes.Length, Sha256 = RuntimePackage.Hex(sha.ComputeHash(bytes)) });
        }
        PackageManifest manifest = new PackageManifest { Version = "2.1.0", ArchiveRoot = "MediaPress-v2.1.0", UncompressedBytes = data.Length + exe.Length + (traversal ? 1 : 0), Parts = parts.ToArray(),
            CriticalFiles = new[] { new CriticalFile { Path = "MediaPress-v2.1.0/MediaPress.exe", Size = exe.Length }, new CriticalFile { Path = "MediaPress-v2.1.0/data.bin", Size = data.Length } } };
        using (SHA256 sha = SHA256.Create()) manifest.ArchiveSha256 = RuntimePackage.Hex(sha.ComputeHash(archive));
        byte[] raw;
        using (MemoryStream memory = new MemoryStream()) { new DataContractJsonSerializer(typeof(PackageManifest)).WriteObject(memory, manifest); raw = memory.ToArray(); }
        File.WriteAllBytes(Path.Combine(partsFolder, "runtime.json"), raw);
        string hash; using (SHA256 sha = SHA256.Create()) hash = RuntimePackage.Hex(sha.ComputeHash(raw));
        return new Fixture { Folder = folder, Hash = hash, Manifest = manifest, Archive = archive };
    }
    static string Prepare(Fixture fixture, Action<int, string> report) { return RuntimePackage.Prepare(fixture.Folder, fixture.Hash, report, CancellationToken.None); }
    public static int Main() {
        AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
        AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
        root = Path.Combine(Path.GetTempPath(), "MediaPressReadyTests-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        int passed = 0;
        Action<string, Action> test = (name, action) => { action(); passed++; Console.WriteLine("PASS " + name); };
        try {
            test("part boundaries, backward/end seeks and real ZIP reading", delegate {
                Fixture f = Make("stream", false);
                using (PartStream stream = new PartStream(Path.Combine(f.Folder, "_internal"), f.Manifest.Parts, null, CancellationToken.None)) {
                    stream.Seek(8170, SeekOrigin.Begin); byte[] read = new byte[20000];
                    Assert(stream.Read(read, 0, read.Length) == read.Length && read.SequenceEqual(f.Archive.Skip(8170).Take(read.Length)), "cross-part bytes");
                    stream.Seek(-32, SeekOrigin.End); Assert(stream.Read(read, 0, 100) == 32, "end read");
                    stream.Seek(0, SeekOrigin.Begin); using (ZipArchive zip = new ZipArchive(stream, ZipArchiveMode.Read, true)) Assert(zip.Entries.Count == 2, "ZIP directory");
                    Reject<IOException>(() => stream.Seek(-1, SeekOrigin.Begin));
                }
            });
            test("offline preparation, Arabic path, exact bytes and cached reopen", delegate {
                Fixture f = Make("ready", false); int progress = 0;
                string exe = Prepare(f, (n, s) => { Assert(n >= progress && n <= 100, "monotonic progress"); progress = n; });
                Assert(File.Exists(exe) && progress == 100, "ready executable");
                byte[] expected = new byte[120000]; new Random(123).NextBytes(expected);
                Assert(File.ReadAllBytes(Path.Combine(Path.GetDirectoryName(exe), "data.bin")).SequenceEqual(expected), "exact extraction");
                DateTime stamp = File.GetLastWriteTimeUtc(exe);
                Assert(Prepare(f, null) == exe && File.GetLastWriteTimeUtc(exe) == stamp, "cached launch");
            });
            test("missing part rejects and clears only owned preparation", delegate {
                Fixture f = Make("missing", false); File.WriteAllText(Path.Combine(f.Folder, "keep.txt"), "keep");
                File.Delete(Path.Combine(f.Folder, "_internal", f.Manifest.Parts[0].Name));
                Reject<FileNotFoundException>(() => Prepare(f, null));
                Assert(File.Exists(Path.Combine(f.Folder, "keep.txt")), "unrelated file kept");
                Assert(Directory.GetDirectories(Path.Combine(f.Folder, "_runtime"), ".prepare-*").Length == 0, "no partial folder");
            });
            test("corrupt part rejects before extraction", delegate {
                Fixture f = Make("corrupt", false); string part = Path.Combine(f.Folder, "_internal", f.Manifest.Parts[0].Name);
                byte[] data = File.ReadAllBytes(part); data[0] ^= 1; File.WriteAllBytes(part, data);
                Reject<InvalidDataException>(() => Prepare(f, null));
            });
            test("mixed manifest rejects", delegate {
                Fixture f = Make("mixed", false); File.AppendAllText(Path.Combine(f.Folder, "_internal", "runtime.json"), " ");
                Reject<InvalidDataException>(() => Prepare(f, null));
            });
            test("ZIP traversal cannot write outside the preparation folder", delegate {
                Fixture f = Make("traversal", true); Reject<InvalidDataException>(() => Prepare(f, null));
                Assert(!File.Exists(Path.Combine(f.Folder, "_runtime", "outside.txt")) && !File.Exists(Path.Combine(f.Folder, "outside.txt")), "outside protected");
            });
            test("cancelled preparation is cleaned and can restart", delegate {
                Fixture f = Make("cancel", false);
                using (CancellationTokenSource token = new CancellationTokenSource()) {
                    Reject<OperationCanceledException>(() => RuntimePackage.Prepare(f.Folder, f.Hash, (n, s) => { if (n >= 16) token.Cancel(); }, token.Token));
                }
                Assert(Directory.GetDirectories(Path.Combine(f.Folder, "_runtime"), ".prepare-*").Length == 0, "cancel cleanup");
                Assert(File.Exists(Prepare(f, null)), "restart");
            });
            test("incomplete cached runtime repairs without overwriting previous files", delegate {
                Fixture f = Make("repair", false); string exe = Prepare(f, null);
                File.WriteAllText(Path.Combine(Path.GetDirectoryName(exe), "personal.txt"), "kept"); File.Delete(exe);
                Assert(File.Exists(Prepare(f, null)), "repaired");
                string previous = Directory.GetDirectories(Path.Combine(f.Folder, "_runtime"), "*-previous-*").Single();
                Assert(File.ReadAllText(Path.Combine(previous, "MediaPress-v2.1.0", "personal.txt")) == "kept", "previous cache preserved");
            });
            Console.WriteLine("OK " + passed + " launcher tests"); return 0;
        } catch (Exception error) { Console.Error.WriteLine(error); return 1; }
        finally { Directory.Delete(root, true); }
    }
}
