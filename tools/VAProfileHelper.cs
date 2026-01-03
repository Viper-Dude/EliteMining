using System;
using System.IO;
using System.Reflection;
using System.Collections.Generic;
using System.Text;

/// <summary>
/// VoiceAttack Profile Helper - Uses VA's internal API to read/write binary profiles
/// </summary>
class VAProfileHelper
{
    static int Main(string[] args)
    {
        Console.WriteLine("VoiceAttack Profile Helper v1.0");
        
        if (args.Length < 2)
        {
            Console.WriteLine("\nUsage:");
            Console.WriteLine("  VAProfileHelper.exe export <profile.vap> <output.json>");
            Console.WriteLine("  VAProfileHelper.exe import <profile.vap> <keybinds.json> <output.vap>");
            return 1;
        }

        string command = args[0].ToLower();
        
        try
        {
            switch (command)
            {
                case "export":
                    if (args.Length < 3)
                    {
                        Console.WriteLine("ERROR: export requires 2 arguments");
                        return 1;
                    }
                    return ExportKeybinds(args[1], args[2]);
                    
                case "import":
                    if (args.Length < 4)
                    {
                        Console.WriteLine("ERROR: import requires 3 arguments");
                        return 1;
                    }
                    return ImportKeybinds(args[1], args[2], args[3]);
                    
                default:
                    Console.WriteLine($"ERROR: Unknown command '{command}'");
                    return 1;
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\nERROR: {ex.Message}");
            Console.WriteLine($"Stack trace: {ex.StackTrace}");
            return 1;
        }
    }
    
    static int ExportKeybinds(string vapPath, string outputPath)
    {
        Console.WriteLine($"\n=== EXPORT KEYBINDS ===");
        Console.WriteLine($"Input:  {vapPath}");
        Console.WriteLine($"Output: {outputPath}");
        
        if (!File.Exists(vapPath))
        {
            Console.WriteLine("ERROR: VAP file not found");
            return 1;
        }
        
        // Load VoiceAttack assembly
        string vaExePath = FindVoiceAttackExe();
        if (vaExePath == null)
        {
            Console.WriteLine("ERROR: Could not find VoiceAttack.exe");
            return 1;
        }
        
        Console.WriteLine($"VA Path: {vaExePath}\n");
        Assembly vaAssembly = Assembly.LoadFrom(vaExePath);
        
        // Load profile
        byte[] profileData = File.ReadAllBytes(vapPath);
        Console.WriteLine($"Loaded {profileData.Length} bytes");
        
        dynamic profile = DeserializeProfile(vaAssembly, profileData);
        
        if (profile == null)
        {
            Console.WriteLine("ERROR: Failed to deserialize profile");
            return 1;
        }
        
        Console.WriteLine("Profile deserialized successfully\n");
        
        // Extract keybinds
        var keybinds = new Dictionary<string, Dictionary<string, object>>();
        
        foreach (var command in GetCommands(profile))
        {
            string name = GetCommandName(command);
            if (string.IsNullOrEmpty(name)) continue;
            
            var kb = ExtractKeybind(command);
            
            if (kb != null && kb.Count > 0)
            {
                keybinds[name] = kb;
                Console.WriteLine($"  {name} -> {kb.Count} keybind(s)");
            }
        }
        
        // Save to JSON
        string json = ToJson(keybinds);
        File.WriteAllText(outputPath, json);
        
        Console.WriteLine($"\n✓ SUCCESS: Exported {keybinds.Count} keybinds");
        return 0;
    }
    
    static int ImportKeybinds(string vapPath, string keybindsPath, string outputPath)
    {
        Console.WriteLine($"\n=== IMPORT KEYBINDS ===");
        Console.WriteLine($"Profile: {vapPath}");
        Console.WriteLine($"Keybinds: {keybindsPath}");
        Console.WriteLine($"Output: {outputPath}");
        
        if (!File.Exists(vapPath))
        {
            Console.WriteLine("ERROR: VAP file not found");
            return 1;
        }
        
        if (!File.Exists(keybindsPath))
        {
            Console.WriteLine("ERROR: Keybinds file not found");
            return 1;
        }
        
        // Load keybinds JSON
        string json = File.ReadAllText(keybindsPath);
        var keybinds = FromJson(json);
        Console.WriteLine($"Loaded {keybinds.Count} keybinds\n");
        
        // Load VoiceAttack assembly
        string vaExePath = FindVoiceAttackExe();
        Console.WriteLine($"VA Path: {vaExePath}\n");
        Assembly vaAssembly = Assembly.LoadFrom(vaExePath);
        
        // Load profile
        byte[] profileData = File.ReadAllBytes(vapPath);
        dynamic profile = DeserializeProfile(vaAssembly, profileData);
        
        if (profile == null)
        {
            Console.WriteLine("ERROR: Failed to deserialize profile");
            return 1;
        }
        
        Console.WriteLine("Profile loaded\n");
        
        // Apply keybinds
        int applied = 0;
        foreach (var command in GetCommands(profile))
        {
            string name = GetCommandName(command);
            if (keybinds.ContainsKey(name))
            {
                ApplyKeybind(command, keybinds[name]);
                Console.WriteLine($"  Applied: {name}");
                applied++;
            }
        }
        
        // Serialize and save
        Console.WriteLine("\nSerializing profile...");
        byte[] newData = SerializeProfile(vaAssembly, profile);
        File.WriteAllBytes(outputPath, newData);
        
        Console.WriteLine($"\n✓ SUCCESS: Applied {applied} keybinds to {outputPath}");
        return 0;
    }
    
    static string FindVoiceAttackExe()
    {
        string[] paths = {
            @"D:\SteamLibrary\steamapps\common\VoiceAttack 2\VoiceAttack.exe",
            @"C:\Program Files\VoiceAttack\VoiceAttack.exe",
            @"C:\Program Files (x86)\VoiceAttack\VoiceAttack.exe"
        };
        
        foreach (string path in paths)
        {
            if (File.Exists(path))
                return path;
        }
        
        return null;
    }
    
    static dynamic DeserializeProfile(Assembly va, byte[] data)
    {
        Console.WriteLine("Searching for Profile type in VoiceAttack assembly...");
        
        Type[] types = va.GetTypes();
        Type profileType = null;
        
        foreach (var t in types)
        {
            if (t.Name == "Profile" && t.IsClass && !t.IsAbstract)
            {
                Console.WriteLine($"Found: {t.FullName}");
                profileType = t;
                break;
            }
        }
        
        if (profileType == null)
        {
            throw new Exception("Could not find Profile type");
        }
        
        // Try various deserialization methods
        MethodInfo[] methods = profileType.GetMethods(BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
        
        foreach (var m in methods)
        {
            if ((m.Name == "Deserialize" || m.Name == "FromBytes" || m.Name == "Load") && 
                m.GetParameters().Length == 1)
            {
                Console.WriteLine($"Using method: {m.Name}");
                try
                {
                    return m.Invoke(null, new object[] { data });
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"  Failed: {ex.Message}");
                }
            }
        }
        
        throw new Exception("Could not find deserialize method");
    }
    
    static IEnumerable<dynamic> GetCommands(dynamic profile)
    {
        var result = new List<dynamic>();
        
        try
        {
            var commands = profile.Commands;
            if (commands != null)
            {
                foreach (var cmd in commands)
                {
                    result.Add(cmd);
                }
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"WARNING: Could not access commands: {ex.Message}");
        }
        
        return result;
    }
    
    static string GetCommandName(dynamic command)
    {
        try
        {
            return command.CommandString ?? command.Name ?? "";
        }
        catch
        {
            return "";
        }
    }
    
    static Dictionary<string, object> ExtractKeybind(dynamic command)
    {
        var kb = new Dictionary<string, object>();
        
        try
        {
            // Keyboard
            if (command.UseShortcut == true && !string.IsNullOrEmpty(command.CommandKeyValue))
            {
                kb["keyboard"] = command.CommandKeyValue;
                kb["keyboard_release"] = command.KeysReleased == true;
            }
            
            // Joystick
            if (command.UseJoystick == true && command.JoystickNumber >= 0)
            {
                kb["joystick_number"] = command.JoystickNumber;
                kb["joystick_button"] = command.JoystickButton;
                kb["joystick_release"] = command.JoystickButtonsReleased == true;
            }
            
            // Mouse
            if (command.UseMouse == true)
            {
                int btn = GetMouseButton(command);
                if (btn > 0)
                {
                    kb["mouse_button"] = btn;
                    kb["mouse_release"] = command.MouseButtonsReleased == true;
                }
            }
        }
        catch { }
        
        return kb;
    }
    
    static void ApplyKeybind(dynamic command, Dictionary<string, object> kb)
    {
        try
        {
            if (kb.ContainsKey("keyboard"))
            {
                command.UseShortcut = true;
                command.CommandKeyValue = kb["keyboard"];
                command.KeysReleased = kb.ContainsKey("keyboard_release") && (bool)kb["keyboard_release"];
            }
            
            if (kb.ContainsKey("joystick_number"))
            {
                command.UseJoystick = true;
                command.JoystickNumber = Convert.ToInt32(kb["joystick_number"]);
                command.JoystickButton = Convert.ToInt32(kb["joystick_button"]);
                command.JoystickButtonsReleased = kb.ContainsKey("joystick_release") && (bool)kb["joystick_release"];
            }
            
            if (kb.ContainsKey("mouse_button"))
            {
                command.UseMouse = true;
                SetMouseButton(command, kb["mouse_button"]);
                command.MouseButtonsReleased = kb.ContainsKey("mouse_release") && (bool)kb["mouse_release"];
            }
        }
        catch { }
    }
    
    static int GetMouseButton(dynamic command)
    {
        for (int i = 1; i <= 9; i++)
        {
            try
            {
                if ((bool)command.GetType().GetProperty($"Mouse{i}").GetValue(command))
                    return i;
            }
            catch { }
        }
        return 0;
    }
    
    static void SetMouseButton(dynamic command, object button)
    {
        int btnNum = Convert.ToInt32(button);
        for (int i = 1; i <= 9; i++)
        {
            try
            {
                command.GetType().GetProperty($"Mouse{i}").SetValue(command, i == btnNum);
            }
            catch { }
        }
    }
    
    static byte[] SerializeProfile(Assembly va, dynamic profile)
    {
        MethodInfo serialize = profile.GetType().GetMethod("Serialize",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        
        if (serialize != null)
        {
            return (byte[])serialize.Invoke(profile, null);
        }
        
        MethodInfo save = profile.GetType().GetMethod("ToBytes",
            BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            
        if (save != null)
        {
            return (byte[])save.Invoke(profile, null);
        }
        
        throw new Exception("Could not find serialize method");
    }
    
    // Simple JSON serialization
    static string ToJson(Dictionary<string, Dictionary<string, object>> data)
    {
        var sb = new StringBuilder();
        sb.AppendLine("{");
        
        bool first = true;
        foreach (var kvp in data)
        {
            if (!first) sb.AppendLine(",");
            first = false;
            
            sb.Append($"  \"{EscapeJson(kvp.Key)}\": {{");
            
            bool firstProp = true;
            foreach (var prop in kvp.Value)
            {
                if (!firstProp) sb.Append(", ");
                firstProp = false;
                
                string value;
                if (prop.Value is string)
                    value = $"\"{EscapeJson(prop.Value.ToString())}\"";
                else if (prop.Value is bool)
                    value = prop.Value.ToString().ToLower();
                else
                    value = prop.Value.ToString();
                
                sb.Append($"\"{prop.Key}\": {value}");
            }
            
            sb.Append("}");
        }
        
        sb.AppendLine();
        sb.AppendLine("}");
        return sb.ToString();
    }
    
    static Dictionary<string, Dictionary<string, object>> FromJson(string json)
    {
        var result = new Dictionary<string, Dictionary<string, object>>();
        
        // Very simple JSON parser for our specific format
        json = json.Trim().Trim('{', '}');
        
        int pos = 0;
        while (pos < json.Length)
        {
            // Find command name
            int nameStart = json.IndexOf('"', pos);
            if (nameStart < 0) break;
            
            int nameEnd = json.IndexOf('"', nameStart + 1);
            if (nameEnd < 0) break;
            
            string cmdName = json.Substring(nameStart + 1, nameEnd - nameStart - 1);
            
            // Find object start
            int objStart = json.IndexOf('{', nameEnd);
            if (objStart < 0) break;
            
            // Find object end
            int objEnd = json.IndexOf('}', objStart);
            if (objEnd < 0) break;
            
            string objJson = json.Substring(objStart + 1, objEnd - objStart - 1);
            
            // Parse properties
            var props = new Dictionary<string, object>();
            string[] parts = objJson.Split(',');
            
            foreach (string part in parts)
            {
                string[] kv = part.Split(':');
                if (kv.Length != 2) continue;
                
                string key = kv[0].Trim().Trim('"');
                string val = kv[1].Trim().Trim('"');
                
                if (val == "true") props[key] = true;
                else if (val == "false") props[key] = false;
                else if (int.TryParse(val, out int intVal)) props[key] = intVal;
                else props[key] = val;
            }
            
            if (props.Count > 0)
            {
                result[cmdName] = props;
            }
            
            pos = objEnd + 1;
        }
        
        return result;
    }
    
    static string EscapeJson(string str)
    {
        return str.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
    }
}
