from PyPDF2 import PdfReader

reader = PdfReader(r'D:\My Apps Work Folder\Elitemining Working folder\Doc\VoiceAttackHelpV2.pdf')

# Read pages 214-220 - Quick Input, Variable Keypress and Hotkey Key Indicators
for i in range(213, 222):
    text = reader.pages[i].extract_text()
    print(f'\n--- PAGE {i+1} ---')
    print(text if text else '(no text)')
