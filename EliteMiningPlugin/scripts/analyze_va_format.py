"""
Analyze VoiceAttack binary format
"""

# Read both files and compare
compressed = open("EliteMining v4.7.5 testing-Profile.vap", "rb").read()
uncompressed = open("EliteMining 4.7.5 testing-Profile.vap", "rb").read()

print(f"Compressed size: {len(compressed):,} bytes")
print(f"Uncompressed size: {len(uncompressed):,} bytes")
print(f"Compression ratio: {len(compressed)/len(uncompressed)*100:.1f}%")

print("\n=== First 100 bytes of compressed (hex) ===")
print(' '.join(f'{b:02x}' for b in compressed[:100]))

print("\n=== First 100 bytes of uncompressed (hex) ===")
print(' '.join(f'{b:02x}' for b in uncompressed[:100]))

print("\n=== Looking for XML markers in compressed ===")
if b'<?xml' in compressed:
    pos = compressed.find(b'<?xml')
    print(f"Found XML at position: {pos}")
    print(f"Context: {compressed[max(0,pos-20):pos+50]}")
else:
    print("No XML marker found")

# Check if it's .NET BinaryFormatter
if compressed[0:1] == b'\x00':
    print("\n=== Possible .NET Binary Serialization ===")
    print(f"First byte is 0x00 - common for .NET serialization")

# Try to find patterns
print("\n=== Looking for 'Profile' string ===")
for encoding in ['utf-8', 'utf-16le', 'utf-16be']:
    try:
        text = compressed.decode(encoding, errors='ignore')
        if 'Profile' in text or 'Command' in text:
            print(f"Found readable text with {encoding}")
            # Show first occurrence
            idx = text.find('Profile') if 'Profile' in text else text.find('Command')
            print(f"Context: {text[max(0,idx-50):idx+50]}")
            break
    except:
        pass
