def solve(data):
    unique_ids = {report['root_id'] for report in data if report['root_id'] is not None}
    return len(unique_ids)