using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Xml;
using LiteDB;

namespace VAProfileReader
{
    // Reads profiles from a COPY of VoiceAttack.dat (LiteDB v5, collection VAMain).
    // Each record's Data is raw deflate of a ZeroFormatter-style object; the field
    // indices and widths below were mapped against VoiceAttack 2 XML exports.
    // Any layout that does not match exits with code 3 instead of guessing.
    internal static class Program
    {
        private const int ExitOk = 0;
        private const int ExitUsage = 1;
        private const int ExitNotFound = 2;
        private const int ExitFormat = 3;
        private const int ExitRefused = 4;

        private enum Kind { Guid, Str, Bool, NBool, Int }

        private sealed class Field
        {
            public readonly int Index;
            public readonly string Name;
            public readonly Kind Kind;
            public Field(int index, string name, Kind kind) { Index = index; Name = name; Kind = kind; }
        }

        private const int IdxCommandString = 1;
        private const int IdxUseShortcut = 8;
        private const int IdxUseJoystick = 24;
        private const int IdxUseMouse = 37;

        // Written in VoiceAttack 2 export element order.
        private static readonly Field[] CommandFields =
        {
            new Field(0, "BaseId", Kind.Guid),
            new Field(1, "CommandString", Kind.Str),
            new Field(4, "Enabled", Kind.Bool),
            new Field(8, "UseShortcut", Kind.Bool),
            new Field(9, "keyValue", Kind.Int),
            new Field(10, "keyShift", Kind.Int),
            new Field(11, "keyAlt", Kind.Int),
            new Field(12, "keyCtrl", Kind.Int),
            new Field(13, "keyWin", Kind.Int),
            new Field(14, "keyPassthru", Kind.NBool),
            new Field(16, "onlyKeyUp", Kind.Bool),
            new Field(24, "UseJoystick", Kind.Bool),
            new Field(25, "joystickNumber", Kind.Int),
            new Field(26, "joystickButton", Kind.Int),
            new Field(27, "joystickNumber2", Kind.Int),
            new Field(28, "joystickButton2", Kind.Int),
            new Field(29, "joystickUp", Kind.Bool),
            new Field(30, "KeepRepeating", Kind.Bool),
            new Field(37, "UseMouse", Kind.Bool),
            new Field(38, "Mouse1", Kind.Bool),
            new Field(39, "Mouse2", Kind.Bool),
            new Field(40, "Mouse3", Kind.Bool),
            new Field(41, "Mouse4", Kind.Bool),
            new Field(42, "Mouse5", Kind.Bool),
            new Field(43, "Mouse6", Kind.Bool),
            new Field(44, "Mouse7", Kind.Bool),
            new Field(45, "Mouse8", Kind.Bool),
            new Field(46, "Mouse9", Kind.Bool),
            new Field(47, "MouseUpOnly", Kind.Bool),
            new Field(48, "MousePassThru", Kind.NBool),
            new Field(49, "joystickExclusive", Kind.Bool),
            new Field(54, "RepeatIfKeysDown", Kind.Bool),
            new Field(55, "RepeatIfMouseDown", Kind.Bool),
            new Field(56, "RepeatIfJoystickDown", Kind.Bool),
            new Field(60, "UseVariableHotkey", Kind.Bool),
            new Field(68, "HotkeyDoubleTapLevel", Kind.Int),
            new Field(69, "MouseDoubleTapLevel", Kind.Int),
            new Field(70, "JoystickDoubleTapLevel", Kind.Int),
            new Field(71, "HotkeyLongTapLevel", Kind.Int),
            new Field(72, "MouseLongTapLevel", Kind.Int),
            new Field(73, "JoystickLongTapLevel", Kind.Int),
            new Field(79, "UseVariableMouseShortcut", Kind.Bool),
            new Field(81, "UseVariableJoystickShortcut", Kind.Bool),
        };

        private const int MinCommandLastIndex = 81;

        private sealed class FormatError : Exception
        {
            public FormatError(string message) : base(message) { }
        }

        private static int Main(string[] args)
        {
            try
            {
                if (args.Length == 3 && args[0] == "list")
                    return Guard(args[1]) ?? List(args[1], args[2]);
                if (args.Length == 4 && args[0] == "export")
                    return Guard(args[1]) ?? Export(args[1], args[2], args[3]);

                Console.Error.WriteLine("Usage:");
                Console.Error.WriteLine("  va_profile_reader list <VoiceAttack.dat copy> <out.xml>");
                Console.Error.WriteLine("  va_profile_reader export <VoiceAttack.dat copy> <profile id> <out.xml>");
                return ExitUsage;
            }
            catch (FormatError ex)
            {
                Console.Error.WriteLine("ERROR: unknown format: " + ex.Message);
                return ExitFormat;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine("ERROR: unreadable: " + ex.GetType().Name + ": " + ex.Message);
                return ExitFormat;
            }
        }

        // VoiceAttack's own folders (live file and Backup) are never opened; callers pass a temp copy.
        private static int? Guard(string datPath)
        {
            string full = Path.GetFullPath(datPath);
            string appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
            foreach (string folder in new[] { "VoiceAttack2", "VoiceAttack" })
            {
                string prefix = Path.Combine(appData, folder).TrimEnd('\\') + "\\";
                if (full.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                {
                    Console.Error.WriteLine("ERROR: refusing to open a file inside " + prefix + "; pass a temporary copy");
                    return ExitRefused;
                }
            }
            if (!File.Exists(full))
            {
                Console.Error.WriteLine("ERROR: file not found: " + full);
                return ExitNotFound;
            }
            return null;
        }

        private static LiteDatabase Open(string datPath)
        {
            return new LiteDatabase(new ConnectionString
            {
                Filename = Path.GetFullPath(datPath),
                ReadOnly = true,
                Connection = ConnectionType.Direct,
            });
        }

        private static IEnumerable<KeyValuePair<string, byte[]>> Records(LiteDatabase db)
        {
            if (!db.CollectionExists("VAMain"))
                throw new FormatError("collection VAMain not found");
            foreach (BsonDocument doc in db.GetCollection("VAMain").FindAll())
            {
                BsonValue version = doc["Version"];
                if (!version.IsInt32 || version.AsInt32 != 1)
                    throw new FormatError("record Version " + version);
                if (!doc["Data"].IsBinary)
                    throw new FormatError("record Data is not binary");
                yield return new KeyValuePair<string, byte[]>(doc["_id"].RawValue.ToString(), Inflate(doc["Data"].AsBinary));
            }
        }

        private static byte[] Inflate(byte[] data)
        {
            using (var input = new MemoryStream(data))
            using (var deflate = new DeflateStream(input, CompressionMode.Decompress))
            using (var output = new MemoryStream())
            {
                deflate.CopyTo(output);
                return output.ToArray();
            }
        }

        private static int List(string datPath, string outPath)
        {
            using (LiteDatabase db = Open(datPath))
            using (XmlWriter xml = CreateWriter(outPath))
            {
                xml.WriteStartElement("Profiles");
                foreach (var record in Records(db))
                {
                    var profile = new Profile(record.Value);
                    int commands = 0, bound = 0;
                    foreach (var cmd in profile.Commands())
                    {
                        if (IsInternal(cmd.String(IdxCommandString)))
                            continue;
                        commands++;
                        if (cmd.Bool(IdxUseShortcut) || cmd.Bool(IdxUseJoystick) || cmd.Bool(IdxUseMouse))
                            bound++;
                    }
                    xml.WriteStartElement("Profile");
                    xml.WriteAttributeString("Id", record.Key);
                    xml.WriteAttributeString("Name", profile.Name ?? "");
                    xml.WriteAttributeString("Commands", commands.ToString());
                    xml.WriteAttributeString("Bound", bound.ToString());
                    xml.WriteEndElement();
                }
                xml.WriteEndElement();
            }
            return ExitOk;
        }

        private static int Export(string datPath, string profileId, string outPath)
        {
            using (LiteDatabase db = Open(datPath))
            {
                foreach (var record in Records(db))
                {
                    if (!string.Equals(record.Key, profileId, StringComparison.OrdinalIgnoreCase))
                        continue;

                    var profile = new Profile(record.Value);
                    using (XmlWriter xml = CreateWriter(outPath))
                    {
                        xml.WriteStartElement("Profile");
                        xml.WriteElementString("Id", record.Key);
                        xml.WriteElementString("Name", profile.Name ?? "");
                        xml.WriteStartElement("Commands");
                        foreach (var cmd in profile.Commands())
                        {
                            if (IsInternal(cmd.String(IdxCommandString)))
                                continue;
                            xml.WriteStartElement("Command");
                            foreach (Field f in CommandFields)
                                xml.WriteElementString(f.Name, cmd.Text(f));
                            xml.WriteEndElement();
                        }
                        xml.WriteEndElement();
                        xml.WriteEndElement();
                    }
                    return ExitOk;
                }
            }
            Console.Error.WriteLine("ERROR: profile not found: " + profileId);
            return ExitNotFound;
        }

        private static bool IsInternal(string commandString)
        {
            string s = (commandString ?? "").Trim();
            return s.StartsWith("((") && s.EndsWith("))");
        }

        private static XmlWriter CreateWriter(string path)
        {
            return XmlWriter.Create(path, new XmlWriterSettings { Indent = true, Encoding = new UTF8Encoding(false) });
        }

        private sealed class Profile
        {
            private readonly Obj _obj;
            public readonly string Name;

            public Profile(byte[] data)
            {
                _obj = new Obj(data, 0, data.Length);
                if (_obj.LastIndex < 2)
                    throw new FormatError("profile has only " + (_obj.LastIndex + 1) + " fields");
                Name = _obj.String(1);
            }

            public IEnumerable<Obj> Commands()
            {
                _obj.Span(2, out int start, out int end);
                byte[] b = _obj.Buffer;
                int count = Obj.I32(b, start, end);
                if (count < 0)
                    yield break;
                int pos = start + 4;
                for (int i = 0; i < count; i++)
                {
                    int size = Obj.I32(b, pos, end);
                    if (size < 8 || pos + size > end)
                        throw new FormatError("command " + i + " size " + size);
                    var cmd = new Obj(b, pos, size);
                    if (cmd.LastIndex < MinCommandLastIndex)
                        throw new FormatError("command " + i + " has only " + (cmd.LastIndex + 1) + " fields");
                    yield return cmd;
                    pos += size;
                }
            }
        }

        private sealed class Obj
        {
            public readonly byte[] Buffer;
            private readonly int _base;
            private readonly int _size;
            private readonly int[] _offsets;
            public int LastIndex => _offsets.Length - 1;

            public Obj(byte[] buffer, int start, int available)
            {
                Buffer = buffer;
                _base = start;
                int limit = start + available;
                _size = I32(buffer, start, limit);
                int last = I32(buffer, start + 4, limit);
                if (_size < 8 || _size > available || last < 0 || 8 + 4 * (last + 1) > _size)
                    throw new FormatError("object header size=" + _size + " last=" + last);
                _offsets = new int[last + 1];
                for (int i = 0; i <= last; i++)
                {
                    int off = I32(buffer, start + 8 + 4 * i, start + _size);
                    if (off < 8 || off > _size)
                        throw new FormatError("field " + i + " offset " + off);
                    _offsets[i] = off;
                }
            }

            public static int I32(byte[] b, int pos, int limit)
            {
                if (pos < 0 || pos + 4 > limit || pos + 4 > b.Length)
                    throw new FormatError("read past end at " + pos);
                return BitConverter.ToInt32(b, pos);
            }

            public void Span(int index, out int start, out int end)
            {
                if (index > LastIndex)
                    throw new FormatError("missing field " + index);
                int off = _offsets[index];
                int next = _size;
                foreach (int o in _offsets)
                    if (o > off && o < next)
                        next = o;
                start = _base + off;
                end = _base + next;
            }

            private int Width(int index, int expected)
            {
                Span(index, out int start, out int end);
                if (end - start != expected)
                    throw new FormatError("field " + index + " width " + (end - start) + ", expected " + expected);
                return start;
            }

            public bool Bool(int index) => ReadBool(Buffer[Width(index, 1)]);

            private static bool ReadBool(byte value)
            {
                if (value > 1)
                    throw new FormatError("bool value " + value);
                return value == 1;
            }

            public string String(int index)
            {
                Span(index, out int start, out int end);
                int len = I32(Buffer, start, end);
                if (len == -1 && end - start == 4)
                    return null;
                if (len < 0 || 4 + len != end - start)
                    throw new FormatError("field " + index + " string length " + len);
                return Encoding.UTF8.GetString(Buffer, start + 4, len);
            }

            public string Text(Field f)
            {
                switch (f.Kind)
                {
                    case Kind.Guid:
                    {
                        int start = Width(f.Index, 16);
                        var bytes = new byte[16];
                        Array.Copy(Buffer, start, bytes, 0, 16);
                        return new Guid(bytes).ToString();
                    }
                    case Kind.Str:
                        return String(f.Index) ?? "";
                    case Kind.Bool:
                        return Bool(f.Index) ? "true" : "false";
                    case Kind.NBool:
                    {
                        int start = Width(f.Index, 2);
                        if (!ReadBool(Buffer[start]))
                            return "";
                        return ReadBool(Buffer[start + 1]) ? "true" : "false";
                    }
                    case Kind.Int:
                        return BitConverter.ToInt32(Buffer, Width(f.Index, 4)).ToString();
                    default:
                        throw new FormatError("kind " + f.Kind);
                }
            }
        }
    }
}
