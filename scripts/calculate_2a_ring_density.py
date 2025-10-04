import math

print("=== CALCULATING DENSITY FOR 'Paesia 2 a A Ring' ===\n")

# From Scan events
inner_radius = 8855600.0  # meters
outer_radius = 23075000.0  # meters
mass_mt = 10135000.0  # Megatons

print("Ring Data from Journals:")
print(f"  Inner Radius: {inner_radius:,} m")
print(f"  Outer Radius: {outer_radius:,} m")
print(f"  Mass: {mass_mt:,} MT")

# Calculate volume (cylindrical ring approximation)
# Volume = π * (R_outer² - R_inner²) * height
# For rings, we use a thin disk, so height = 1 meter for density calculation
volume_m3 = math.pi * (outer_radius**2 - inner_radius**2) * 1.0

print(f"\nVolume (1m height): {volume_m3:,.0f} m³")

# Convert mass from Megatons to kg
# 1 Megaton = 1,000,000,000 kg = 1e9 kg
mass_kg = mass_mt * 1e9

print(f"Mass in kg: {mass_kg:,.0f} kg")

# Calculate density (kg/m³)
density = mass_kg / volume_m3

print(f"\n✅ Calculated Density: {density:.6f} kg/m³")

print("\n" + "=" * 70)
print("\nFor database (default values):")
print(f"  ring_type: 'Icy'")
print(f"  ls_distance: 833.224795  (average from scan results)")
print(f"  density: {density:.6f}")
print(f"  inner_radius: {inner_radius}")
print(f"  outer_radius: {outer_radius}")
print(f"  ring_mass: {mass_mt}")
