content = open('desktop/app/project_file.py', 'r', encoding='utf-8').read()
for i, line in enumerate(content.split('\n'), 1):
    if 'REQUIRED_SECTIONS' in line:
        print(f'Line {i}: {repr(line)}')
        print(f'Line {i} bytes: {line.encode("utf-8")}')
