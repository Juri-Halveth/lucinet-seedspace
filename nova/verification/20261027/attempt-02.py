def solve(data):
    unique_ids = set()
    for report in data:
        root_id = report['root_id']
        if root_id is not None:
            unique_ids.add(root_id)
    return len(unique_ids)