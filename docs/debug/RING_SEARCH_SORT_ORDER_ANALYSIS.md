# Ring Search Current Sort Order Analysis

**Date:** October 2, 2025  
**File:** `app/ring_finder.py`

---

## 🔍 CURRENT SORT ORDER

### **SQL Query Sort (Line 1593, 1604):**
```sql
ORDER BY 
    hotspot_count DESC,    -- 1st: Highest hotspot count first
    system_name,           -- 2nd: System name (alphabetical)
    body_name              -- 3rd: Ring/Body name (alphabetical)
```

### **Python Post-Processing Sort (Line 1713-1716):**

**Two Different Behaviors:**

#### **When searching for SPECIFIC material:**
```python
# Line 1713
user_hotspots.sort(key=lambda x: (-x['count'], x['distance']))
```
**Order:**
1. **Hotspot count** (highest first) - `DESC`
2. **Distance** (closest first) - `ASC`

#### **When material = "All Materials":**
```python
# Line 1716
user_hotspots.sort(key=lambda x: (x['distance'], -x['count']))
```
**Order:**
1. **Distance** (closest first) - `ASC`
2. **Hotspot count** (highest first) - `DESC`

### **Additional Sort (Line 810):**
```python
# In _search_user_database_first
compatible_results.sort(key=lambda x: float(x.get('distance', 999)))
```
**Order:** Distance only (closest first)

---

## 📊 ACTUAL SORT ORDER USED

### **The Final Sort Wins:**

The Python sort **overrides** the SQL ORDER BY.

**Current behavior:**

| Search Type | Sort Priority 1 | Sort Priority 2 | Sort Priority 3 |
|-------------|----------------|-----------------|-----------------|
| **Specific Material** (e.g., "Platinum") | Hotspot Count ↓ | Distance ↑ | - |
| **All Materials** | Distance ↑ | Hotspot Count ↓ | - |

**Legend:**
- ↓ = Descending (highest first)
- ↑ = Ascending (lowest first)

---

## ❓ IS THIS WHAT YOU WANT?

### **Your Requested Order:**
> "System name, Ring name"

### **Current Order:**
- ❌ NOT System name, Ring name
- ✅ Distance-based OR Count-based

---

## 🎯 DISCREPANCY FOUND!

**You want:**
```
Sort by:
1. System name (alphabetical)
2. Ring name (alphabetical)
```

**Current code does:**
```
Sort by:
1. Distance (closest first) or Hotspot count (most first)
2. Hotspot count (most first) or Distance (closest first)
```

---

## 💡 PROPOSED FIX

### **Option A: Always Sort by System → Ring**
```python
# Replace line 1713-1716 with:
user_hotspots.sort(key=lambda x: (
    x['systemName'].lower(),    # 1st: System name
    x['bodyName'].lower()        # 2nd: Ring name
))
```

**Result:**
```
Delkar (7 A Ring)
Delkar (8 A Ring)
HIP 12345 (A Ring)
Sol (Saturn A Ring)
```

---

### **Option B: Sort by System → Ring, then Distance**
```python
user_hotspots.sort(key=lambda x: (
    x['systemName'].lower(),    # 1st: System name
    x['bodyName'].lower(),       # 2nd: Ring name
    x['distance']                # 3rd: Distance (tie-breaker)
))
```

**Result:** Same system/ring grouping, but if duplicates exist, closest first

---

### **Option C: Keep Distance Primary, Add System/Ring Secondary**
```python
user_hotspots.sort(key=lambda x: (
    x['distance'],               # 1st: Distance (closest first)
    x['systemName'].lower(),     # 2nd: System name (tie-breaker)
    x['bodyName'].lower()        # 3rd: Ring name (tie-breaker)
))
```

**Result:** Closest systems first, but within same distance, alphabetical

---

## 🤔 QUESTIONS FOR YOU

1. **Do you want distance to be PRIMARY or SECONDARY sort?**
   - Primary: Closest systems at top (current behavior)
   - Secondary: Alphabetical systems at top, distance as tie-breaker

2. **Should specific material searches behave differently?**
   - Currently: Specific material = hotspot count first
   - Should it be: System name first (always)?

3. **What about hotspot count?**
   - Should it factor into sort at all?
   - Or just display it but sort by system/ring?

---

## 📋 EXAMPLE COMPARISONS

### **Current Sort (All Materials):**
```
Distance  System        Ring
─────────────────────────────────
0.0 LY    Delkar        7 A Ring
0.0 LY    Delkar        8 A Ring
5.2 LY    HIP 12345     A Ring
8.6 LY    Sol           Saturn A Ring
```
✅ Distance primary

### **Your Requested Sort:**
```
System      Ring           Distance
─────────────────────────────────────
Delkar      7 A Ring       0.0 LY
Delkar      8 A Ring       0.0 LY
HIP 12345   A Ring         5.2 LY
Sol         Saturn A Ring  8.6 LY
```
✅ System name primary, Ring name secondary

### **Hybrid Sort (Distance → System → Ring):**
```
Distance  System        Ring
─────────────────────────────────
0.0 LY    Delkar        7 A Ring
0.0 LY    Delkar        8 A Ring
5.2 LY    HIP 12345     A Ring
8.6 LY    Sol           Saturn A Ring
```
✅ Distance primary, but alphabetical within same distance

---

## 🎯 MY RECOMMENDATION

**For ring type searches (when showing ALL rings of a type):**

```python
if material_filter == "All Materials":
    # User browsing ring types - alphabetical makes sense
    user_hotspots.sort(key=lambda x: (
        x['systemName'].lower(),
        x['bodyName'].lower()
    ))
else:
    # User searching for specific material - distance matters more
    user_hotspots.sort(key=lambda x: (
        -x['count'],          # Best hotspots first
        x['distance']         # Closest first
    ))
```

**Rationale:**
- Browsing ring types → Alphabetical (easier to navigate)
- Hunting specific material → Distance/quality (practical mining)

---

## ✅ WHAT DO YOU PREFER?

Please confirm which sort order you want:

**A)** System → Ring (always alphabetical)  
**B)** Distance → System → Ring (closest first, then alphabetical)  
**C)** Different for "All Materials" vs specific materials  
**D)** Something else?

---

*Waiting for your confirmation before implementing!*
