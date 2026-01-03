using System;
using System.IO;

/// <summary>
/// EliteMining VoiceAttack Plugin
/// Handles all EliteMining commands by writing to Variables files
/// that the Python app monitors.
/// </summary>
public class EliteMiningPlugin
    {
        private static string pluginName = "EliteMining Plugin";
        private static string pluginVersion = "1.0.0";
        private static string pluginAuthor = "Viper-Dude";

        /// <summary>
        /// Returns unique plugin ID (REQUIRED by VoiceAttack v4)
        /// </summary>
        public static Guid VA_Id()
        {
            return new Guid("{A5B2C3D4-E5F6-4A5B-8C9D-1E2F3A4B5C6D}");
        }

        /// <summary>
        /// Returns plugin display name for VoiceAttack
        /// </summary>
        public static string VA_DisplayName()
        {
            return $"{pluginName} v{pluginVersion} - {pluginAuthor}";
        }

        /// <summary>
        /// Returns plugin information for VoiceAttack
        /// </summary>
        public static string VA_DisplayInfo()
        {
            return $"{pluginName}\r\n" +
                   $"Version: {pluginVersion}\r\n" +
                   $"Author: {pluginAuthor}\r\n\r\n" +
                   "This plugin routes all EliteMining commands to the Python application.";
        }

        /// <summary>
        /// Called when VoiceAttack initializes
        /// </summary>
        public static void VA_Init1(dynamic vaProxy)
        {
            vaProxy.WriteToLog($"EliteMining Plugin {pluginVersion} initialized", "blue");
        }

        /// <summary>
        /// Called when VoiceAttack shuts down
        /// </summary>
        public static void VA_Exit1(dynamic vaProxy)
        {
            vaProxy.WriteToLog("EliteMining Plugin shutting down", "blue");
        }

        /// <summary>
        /// Called when user executes "stop all commands" (REQUIRED by VoiceAttack v4)
        /// </summary>
        public static void VA_StopCommand()
        {
            // Nothing to do - our plugin doesn't run long operations
        }

        /// <summary>
        /// Main entry point for all plugin commands
        /// </summary>
        public static void VA_Invoke1(dynamic vaProxy)
        {
            try
            {
                // Get the command context from VA
                string commandContext = vaProxy.Context ?? "";
                
                // Get base path for EliteMining - VA_APPS is in SessionState
                string vaAppsPath = vaProxy.SessionState.ContainsKey("VA_APPS") 
                    ? vaProxy.SessionState["VA_APPS"]?.ToString() 
                    : null;
                
                if (string.IsNullOrEmpty(vaAppsPath))
                {
                    vaProxy.WriteToLog("ERROR: VA_APPS path not found in SessionState", "red");
                    return;
                }

                string eliteMiningPath = Path.Combine(vaAppsPath, "EliteMining");
                string variablesPath = Path.Combine(eliteMiningPath, "Variables");

                // Ensure Variables directory exists
                Directory.CreateDirectory(variablesPath);

                // Route command based on context
                RouteCommand(vaProxy, commandContext, variablesPath);
            }
            catch (Exception ex)
            {
                vaProxy.WriteToLog($"EliteMining Plugin Error: {ex.Message}", "red");
            }
        }

        /// <summary>
        /// Routes commands to appropriate handlers
        /// </summary>
        private static void RouteCommand(dynamic vaProxy, string context, string variablesPath)
        {
            // Get parameters from VA
            string param1 = vaProxy.GetText("EM.Param1") ?? "";
            string param2 = vaProxy.GetText("EM.Param2") ?? "";
            int paramInt = vaProxy.GetInt("EM.ParamInt") ?? 0;

            switch (context.ToUpper())
            {
                // ============================================
                // UI COMMANDS
                // ============================================
                case "TAB":
                    WriteFile(Path.Combine(variablesPath, "eliteMiningCommand.txt"), $"TAB:{param1.ToUpper()}");
                    break;

                case "SESSION":
                    WriteFile(Path.Combine(variablesPath, "eliteMiningCommand.txt"), $"SESSION:{param1.ToUpper()}");
                    break;

                case "SETTINGS":
                    WriteFile(Path.Combine(variablesPath, "eliteMiningCommand.txt"), $"SETTINGS:{param1.ToUpper()}");
                    break;

                case "ANNOUNCEMENT":
                    // Announcement presets: ANNOUNCEMENT:LOAD:N
                    WriteFile(Path.Combine(variablesPath, "eliteMiningCommand.txt"), $"ANNOUNCEMENT:{param1}:{paramInt}");
                    break;

                case "APP":
                    WriteFile(Path.Combine(variablesPath, "eliteMiningCommand.txt"), $"APP:{param1.ToUpper()}");
                    break;

                // ============================================
                // KEYBIND MANAGEMENT
                // ============================================
                case "EXPORT_KEYBINDS":
                    // Trigger VA command to export keybinds
                    // The VA command will read all command keybinds and save to file
                    vaProxy.WriteToLog("Exporting keybinds...", "blue");
                    vaProxy.Command.Execute("((Export All Keybinds))", true); // Wait for completion
                    WriteFile(Path.Combine(variablesPath, "keybind_export_status.txt"), "SUCCESS");
                    break;

                case "IMPORT_KEYBINDS":
                    // Trigger VA command to import keybinds
                    // The VA command will read keybinds from file and apply to commands
                    vaProxy.WriteToLog("Importing keybinds...", "blue");
                    vaProxy.Command.Execute("((Import All Keybinds))", true); // Wait for completion
                    WriteFile(Path.Combine(variablesPath, "keybind_import_status.txt"), "SUCCESS");
                    break;

                // ============================================
                // GAME ACTION SEQUENCES
                // ============================================
                case "DEPLOY_WEAPONS":
                    // Read any config (if needed in future)
                    // For now, just set the pause duration
                    vaProxy.SetDecimal("EM.WeaponDeployPause", 1.0m); // 1 second pause
                    
                    // Commands to kill
                    vaProxy.SetText("EM.KillCommands", "Reset mining sequence;Start Scanning for Cores;Start Pulse wave scanning;Start mining sequence");
                    
                    // Sequence actions
                    vaProxy.SetText("EM.Action1", "STOP_LASERS");
                    vaProxy.SetText("EM.Action2", "KILL_SEQUENCES");
                    vaProxy.SetText("EM.Action3", "PAUSE");
                    vaProxy.SetText("EM.Action4", "DEPLOY_HARDPOINTS");
                    vaProxy.SetText("EM.Action5", "SET_FG_WEAPONS");
                    vaProxy.SetText("EM.Action6", "CHECK_ANALYSIS_MODE");
                    vaProxy.SetText("EM.Action7", "DONE");
                    
                    vaProxy.SetBoolean("EM.Ready", true);
                    break;

                // ============================================
                // FIREGROUP COMMANDS
                // ============================================
                case "SETFIREGROUP":
                    string fgTarget = param1.ToLower(); // discovery, lasers, prospector, pwa, seismic, ssm, weapons
                    string fgValue = param2.ToLower();   // alpha, bravo, charlie, etc.
                    WriteFile(Path.Combine(variablesPath, $"fg{fgTarget}.txt"), fgValue);
                    vaProxy.WriteToLog($"Firegroup for {fgTarget} set to {fgValue}", "blue");
                    break;

                // ============================================
                // FIRE BUTTON COMMANDS
                // ============================================
                case "SETFIREBUTTON":
                    string btnTarget = param1.ToLower(); // discovery, lasers, prospector, pwa
                    string btnValue = param2.ToLower();   // primary, secondary
                    WriteFile(Path.Combine(variablesPath, $"btn{btnTarget}.txt"), btnValue);
                    vaProxy.WriteToLog($"Fire button for {btnTarget} set to {btnValue}", "blue");
                    break;

                // ============================================
                // TIMER COMMANDS
                // ============================================
                case "SETTIMER":
                    string timerTarget = param1.ToLower(); // lasermining, cargoscoop, etc.
                    WriteFile(Path.Combine(variablesPath, $"timer{timerTarget}.txt"), paramInt.ToString());
                    vaProxy.WriteToLog($"Timer for {timerTarget} set to {paramInt} seconds", "blue");
                    break;

                // ============================================
                // TOGGLE COMMANDS
                // ============================================
                case "SETTOGGLE":
                    string toggleTarget = param1.ToLower(); // cargoscoop, prospectortarget, etc.
                    WriteFile(Path.Combine(variablesPath, $"toggle{toggleTarget}.txt"), paramInt.ToString());
                    vaProxy.WriteToLog($"Toggle for {toggleTarget} set to {paramInt}", "blue");
                    break;

                // ============================================
                // SWAP/SWITCH COMMANDS
                // ============================================
                case "SWAPFIREBUTTON":
                    string swapTarget = param1.ToLower();
                    string currentValue = ReadFile(Path.Combine(variablesPath, $"btn{swapTarget}.txt"));
                    string newValue = (currentValue == "primary") ? "secondary" : "primary";
                    WriteFile(Path.Combine(variablesPath, $"btn{swapTarget}.txt"), newValue);
                    vaProxy.WriteToLog($"Fire button for {swapTarget} swapped to {newValue}", "blue");
                    break;

                default:
                    vaProxy.WriteToLog($"Unknown command context: {context}", "orange");
                    break;
            }
        }

        /// <summary>
        /// Writes text to file atomically
        /// </summary>
        private static void WriteFile(string path, string content)
        {
            try
            {
                string dir = Path.GetDirectoryName(path);
                if (!string.IsNullOrEmpty(dir))
                {
                    Directory.CreateDirectory(dir);
                }

                string tempPath = path + ".tmp";
                File.WriteAllText(tempPath, content);
                if (File.Exists(path))
                {
                    File.Delete(path);
                }
                File.Move(tempPath, path);
            }
            catch (Exception ex)
            {
                // Log the error but don't crash
                System.Diagnostics.Debug.WriteLine($"WriteFile error: {ex.Message}");
                // Fallback to direct write
                try
                {
                    File.WriteAllText(path, content);
                }
                catch
                {
                    // Give up silently
                }
            }
        }

        /// <summary>
        /// Reads text from file
        /// </summary>
        private static string ReadFile(string path)
        {
            try
            {
                if (File.Exists(path))
                {
                    return File.ReadAllText(path).Trim();
                }
            }
            catch (Exception)
            {
                // Ignore read errors
            }
            return "";
        }
    }