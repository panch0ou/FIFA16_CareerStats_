"""Only the FIFA DATA metadata used by Career Stats."""
from transferengine.schema import metadata_tables

METADATA = 'data/db/fifa_ng_db-meta.xml'
REQUIRED = {
    'career_users': ('clubteamid', 'seasoncount'),
    'career_calendar': ('currdate', 'setupdate'),
    'teamplayerlinks': ('teamid', 'playerid'),
}
OPTIONAL = {
    'career_users': ('leagueid', 'primarycompobjid'),
    'career_calendar': ('enddate',),
    'players': ('playerid', 'preferredposition1'),
    'leagues': ('leagueid', 'leaguename', 'countryid', 'level'),
    'career_competitionprogress': ('compobjid', 'compshortname', 'teamid', 'season'),
}


class CareerSchemaError(ValueError):
    pass


def short_code(value):
    return isinstance(value, str) and len(value) == 4 and all(ord(ch) <= 255 for ch in value)


def field_metadata(table, name, optional):
    fields = [field for field in table.findall('./fields/field') if field.get('name') == name]
    label = f'{table.get("name")}.{name}'
    if len(fields) != 1:
        if optional:
            return None
        raise CareerSchemaError(f'Missing or ambiguous save field: {label}.')
    meta = fields[0].attrib
    string = name in ('leaguename', 'compshortname')
    expected_type = 'DBOFIELDTYPE_STRING' if string else 'DBOFIELDTYPE_INTEGER'
    try:
        depth = int(meta['depth'])
        int(meta.get('rangelow', 0))
        valid_depth = depth > 0 and depth % 8 == 0 if string else 1 <= depth <= 32
        if meta.get('type') != expected_type or not valid_depth or not short_code(meta.get('shortname')):
            raise ValueError
    except (KeyError, ValueError):
        if optional:
            return None
        raise CareerSchemaError(f'Invalid save field definition: {label}.') from None
    return meta | {'career_type': 0 if string else 3, 'optional': optional}


def load(path):
    try:
        tables = metadata_tables(path)
    except FileNotFoundError as exc:
        raise CareerSchemaError('The FIFA save metadata XML is missing.') from exc
    except (OSError, ValueError) as exc:
        raise CareerSchemaError('The FIFA save metadata XML could not be read.') from exc
    schema = {}
    for name in dict.fromkeys((*REQUIRED, *OPTIONAL)):
        required = REQUIRED.get(name, ())
        matches = [table for table in tables if table.get('name') == name]
        if len(matches) != 1 or not short_code(matches[0].get('shortname')):
            if required:
                raise CareerSchemaError(f'Missing or invalid save table definition: {name}.')
            continue
        table = matches[0]
        code = table.get('shortname')
        if sum(item.get('shortname') == code for item in tables) != 1:
            if required:
                raise CareerSchemaError(f'Ambiguous save table code: {name}.')
            continue
        fields = {}
        all_fields = table.findall('./fields/field')
        for field in (*required, *OPTIONAL.get(name, ())):
            optional = field not in required
            meta = field_metadata(table, field, optional)
            if meta is None:
                continue
            key = meta['shortname']
            if sum(item.get('shortname') == key for item in all_fields) != 1:
                if optional:
                    continue
                raise CareerSchemaError(f'Ambiguous save field code: {name}.{field}.')
            fields[key] = meta
        schema[code] = {'name': name, 'fields': fields}
    return schema


def verify_snapshot(snapshot):
    for name, fields in REQUIRED.items():
        table = snapshot.table(name)
        for name in fields:
            field = table.get_field(name)
            if field.type != 3:
                raise CareerSchemaError(f'Expected a numeric save field: {table.name}.{name}.')
