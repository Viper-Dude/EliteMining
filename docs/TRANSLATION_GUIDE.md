# EliteMining Translation Guide

Thank you for helping translate EliteMining! This guide explains how to contribute translations.

## Supported Languages

| Code | Language | Status |
|------|----------|--------|
| en | English | ✅ Complete (Source) |
| de | German | ✅ Complete |
| fr | French | 🔴 Needed |
| es | Spanish | 🔴 Needed |
| ru | Russian | 🔴 Needed |
| pt | Portuguese | 🔴 Needed |

---

## How to Contribute

### Step 1: Fork the Repository
1. Go to https://github.com/Viper-Dude/EliteMining
2. Click **Fork** (top right)
3. Clone your fork locally

### Step 2: Create Translation Files
Navigate to `app/localization/` and copy the English files:

```bash
# For UI strings
cp strings_en.json strings_XX.json

# For material names
cp materials_en.json materials_XX.json
```

Replace `XX` with your language code (e.g., `fr` for French, `es` for Spanish).

### Step 3: Translate the Strings

Open your new JSON file and translate the values (right side), keeping the keys (left side) unchanged.

**Example:**
```json
// strings_en.json (DO NOT CHANGE)
"search": "Search",
"cancel": "Cancel",

// strings_fr.json (YOUR TRANSLATION)
"search": "Rechercher",
"cancel": "Annuler",
```

### Step 4: Update the Meta Section
At the top of the file, update the `meta` section:

```json
{
  "meta": {
    "language": "French",
    "code": "fr",
    "version": "1.0",
    "author": "Your Name"
  },
  ...
}
```

### Step 5: Submit a Pull Request
1. Commit your changes
2. Push to your fork
3. Open a Pull Request to the main repository
4. Describe what language you added

---

## Translation Files

### `strings_XX.json` - UI Strings
Contains all user interface text:
- Button labels
- Tab names
- Status messages
- Tooltips
- Dialog text

### `materials_XX.json` - Material Names
Contains Elite Dangerous material names and abbreviations:
- Mineral names (must match in-game exactly!)
- Abbreviations for display in tables
- Reverse mapping for database queries

---

## Important Guidelines

### ✅ DO:
- Keep JSON structure exactly the same
- Translate only the **values** (right side of `:`)
- Use the exact in-game material names for your language
- Test your translation if possible
- Keep placeholders like `{count}`, `{system}`, `{distance}` unchanged

### ❌ DON'T:
- Change the **keys** (left side of `:`)
- Remove or add entries
- Change the file structure
- Translate placeholder variables

### Example with Placeholders:
```json
// English
"results_found": "Found {count} results near '{system}'"

// French - keep {count} and {system} unchanged!
"results_found": "Trouvé {count} résultats près de '{system}'"
```

---

## Testing Your Translation

1. Place your files in `app/localization/`
2. Add your language to the supported list in `app/localization/__init__.py`
3. Run EliteMining and switch to your language
4. Check all tabs and dialogs for correct display

---

## Material Names Reference

Material names must match the in-game names exactly. Here are the English names to translate:

| English | Notes |
|---------|-------|
| Platinum | |
| Painite | |
| Low Temperature Diamonds | Often abbreviated as "LTD" |
| Void Opals | |
| Alexandrite | |
| Grandidierite | |
| Musgravite | |
| Rhodplumsite | |
| Serendibite | |
| Monazite | |
| Benitoite | |
| Bromellite | |
| Tritium | |
| Gold | |
| Silver | |
| Osmium | |
| Palladium | |
| Praseodymium | |
| Samarium | |
| Bertrandite | |
| Coltan | |
| Gallite | |
| Indite | |
| Uraninite | |
| Methane Clathrate | |
| Methanol Monohydrate Crystals | |
| Lithium Hydroxide | |
| Hydrogen Peroxide | |
| Liquid Oxygen | |
| Water | |

---

## Need Help?

- **Discord:** https://discord.gg/5dsF3UshRR
- **GitHub Issues:** https://github.com/Viper-Dude/EliteMining/issues
- **Discussions:** https://github.com/Viper-Dude/EliteMining/discussions

---

## Credits

All translators will be credited in the About tab and README!

Thank you for helping make EliteMining accessible to more commanders! o7
