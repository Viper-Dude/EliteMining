# 📋 Reports Tab Column Maintenance Guide

## ⚠️ CRITICAL: When Adding/Removing/Reordering Columns

When modifying the Reports tab columns, **ALL** of the following must be updated to prevent bugs:

---

## **1. Column Definition (prospector_panel.py ~line 4600)**

```python
self.reports_tree_tab = ttk.Treeview(main_frame, columns=(
    "date", "duration", "session_type", "ship", "system", "body", 
    "tons", "tph", "asteroids", "materials", "hit_rate", "quality", 
    "cargo", "prospects", "eng_materials", "comment", "enhanced"
), ...)
```

**Current Order (17 columns):**
0. date
1. duration
2. session_type
3. ship
4. system
5. body
6. tons
7. tph
8. asteroids (Prospected)
9. materials (Mat Types)
10. hit_rate
11. quality
12. cargo
13. prospects (Limpets)
14. eng_materials (Engineering Materials)
15. comment (Comment)
16. enhanced (Detail Report)

---

## **2. Column Headings (~line 4610)**

```python
self.reports_tree_tab.heading("date", text="Date/Time")
self.reports_tree_tab.heading("duration", text="Duration")
self.reports_tree_tab.heading("session_type", text="Type")
...
```

Must match column definition order!

---

## **3. Column Widths (~line 4706)**

```python
self.reports_tree_tab.column("date", width=105, ...)
self.reports_tree_tab.column("duration", width=80, ...)
...
```

Must match column definition order!

---

## **4. Values Insert (~line 5873)**

```python
item_id = self.reports_tree_tab.insert("", "end", values=(
    session['date'],           # 0: date
    session['duration'],       # 1: duration
    session_type_display,      # 2: session_type
    ship_name,                 # 3: ship
    session['system'],         # 4: system
    session['body'],           # 5: body
    session['tons'],           # 6: tons
    session['tph'],            # 7: tph
    session['asteroids'],      # 8: asteroids
    session['materials'],      # 9: materials
    session['hit_rate'],       # 10: hit_rate
    session['quality'],        # 11: quality
    session['cargo'],          # 12: cargo
    session['prospects'],      # 13: prospects
    eng_materials_display,     # 14: eng_materials
    '💬' if comment else '',   # 15: comment
    ""                         # 16: enhanced
))
```

**CRITICAL:** Values must be in EXACT same order as column definition!

---

## **5. CSV Fieldnames (~line 3786 and ~line 7307)**

```python
fieldnames = ['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph',
            'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 
            'avg_quality_percent', 'total_average_yield', 'best_material', 
            'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 
            'engineering_materials', 'comment']
```

**Note:** CSV order doesn't need to match tree order (DictWriter handles mapping), but ensure consistency across all CSV write locations.

---

## **6. Hardcoded Position References** ⚠️ **MOST COMMON BUG SOURCE!**

Search for these patterns and update position numbers:

### **Comment Column (position 15):**
- `_edit_comment()` (~line 7095): `new_values[15] = comment_display`
- Any code that accesses `values[15]` expecting comment

### **Engineering Materials Column (position 14):**
- Any code accessing `values[14]` expecting eng_materials

### **Enhanced Report Column (position 16):**
- Any code accessing `values[16]` expecting enhanced status

**Search patterns to check:**
```python
values[14]  # Hard-coded position access
new_values[15]  # Hard-coded position modification
len(new_values) > 14  # Position-based validation
```

---

## **7. Session Data Dictionary Keys**

Ensure these match between:
- Data reading (CSV/TXT parsing)
- Tree insertion
- Comment/edit handlers

```python
session_data = {
    'date': ...,
    'duration': ...,
    'system': ...,
    'body': ...,
    'tons': ...,
    'tph': ...,
    'asteroids': ...,
    'materials': ...,
    'hit_rate': ...,
    'quality': ...,
    'cargo': ...,
    'prospects': ...,
    'engineering_materials': ...,  # Note: uses underscore
    'comment': ...,
    'timestamp_raw': ...
}
```

---

## **Checklist When Adding a Column:**

- [ ] Add to column definition tuple (line 4600)
- [ ] Add heading (line 4610)
- [ ] Add column width (line 4706)
- [ ] Add to values insert (line 5873) in correct position
- [ ] Add to CSV fieldnames if needed (line 3786, 7307)
- [ ] Update ALL hardcoded position references (+1 for all positions after insertion point)
- [ ] Update session data dictionary keys
- [ ] Test: Create new session with comment
- [ ] Test: Edit existing session comment
- [ ] Test: Sort by new column
- [ ] Test: CSV export/import

---

## **Common Bugs After Column Changes:**

1. **Comment icon appears in wrong column** → Check `_edit_comment()` position index
2. **Values misaligned** → Check values insert order vs column definition
3. **Sorting broken** → Check column name in sort handlers
4. **CSV data missing** → Check fieldnames order
5. **Old reports show wrong data** → Check backward compatibility handlers

---

## **Testing Protocol:**

After column changes, test these scenarios:
1. Start new mining session with comment
2. Edit existing session comment
3. Sort by all columns
4. Filter reports
5. Export to CSV
6. Rebuild CSV from files
7. Check old reports display correctly

---

## **Last Updated:** 2025-10-24
**Current Column Count:** 17
**Last Change:** Fixed comment column position after session_type addition
