from pathlib import Path
import xml.etree.ElementTree as ET

def metadata_tables(path):
 with Path(path).open('rb') as stream:
  raw=stream.read(20_000_001)
 if len(raw)>20_000_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Unsupported XML metadata.')
 try:
  return ET.fromstring(raw).findall('.//table')
 except ET.ParseError as exc:
  raise ValueError('Malformed XML metadata.') from exc


def load_schema(path):
 if path is None:return {}
 return {t.get('shortname'):{'name':t.get('name'), 'fields':{f.get('shortname'):dict(f.attrib) for f in t.findall('./fields/field')}} for t in metadata_tables(path)}
