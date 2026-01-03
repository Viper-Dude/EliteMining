# VoiceAttack Profile Format - Research Summary

## The Problem
VoiceAttack stores profiles in two formats:
1. **.VAP export files** - Proprietary binary (NOT gzip, NOT deflate)
2. **VoiceAttack.dat** - .NET BinaryFormatter serialization

Neither can be read with standard Python libraries.

## Solution Options

### Option 1: Use .NET Interop (pythonnet)
Create C# helper to deserialize VoiceAttack.dat:

```csharp
using System.Runtime.Serialization.Formatters.Binary;

BinaryFormatter formatter = new BinaryFormatter();
var data = formatter.Deserialize(stream);
// Extract profile XML from deserialized object
```

### Option 2: Require Uncompressed Export
**SIMPLEST - Use this for now:**
- Users export profile as uncompressed XML
- Updater processes XML
- User re-imports
- Works with EliteAPI after import

### Option 3: Reverse Engineer Format
Study VoiceAttack's assembly to understand serialization structure.

## Recommendation

**START WITH OPTION 2** (uncompressed XML):
1. ✅ Works immediately
2. ✅ No dependencies
3. ✅ User imports once after update
4. ✅ EliteAPI works after import

**LATER:** Add Option 1 for advanced users who want zero-click updates.

## Why Other Apps Work

Apps that read compressed VAP likely:
- Use .NET (C#/VB.NET) natively
- Or reverse-engineered the format
- Or use VoiceAttack's SDK/API (if exists)

We can add .NET support later via pythonnet if needed.
