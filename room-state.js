export const ROOM_SCHEMA = 'seedspace.room.v1';

export function encodeRoom(instances, width, height) {
  if (!(width > 0 && height > 0)) throw new Error('Invalid room dimensions');
  const blueprintIds = instances.map(item => item.blueprint.id);
  if (new Set(blueprintIds).size !== blueprintIds.length) throw new Error('Duplicate blueprint');
  const items = instances.map(item => ({
    id: item.id,
    blueprintId: item.blueprint.id,
    x: item.x / width,
    y: item.y / height,
    visible: item.visible
  }));
  return JSON.stringify({schema: ROOM_SCHEMA, items});
}

// Old v1 rooms may contain repeats. Keep the latest placement of each type,
// while preserving the relative order of all surviving objects.
export function latestByBlueprint(records) {
  return records.filter((record, index) =>
    records.findLastIndex(item => item.blueprintId === record.blueprintId) === index);
}

export function decodeRoom(raw, allowedIds, width, height) {
  if (!(width > 0 && height > 0)) throw new Error('Invalid room dimensions');
  const data = JSON.parse(raw);
  if (data?.schema !== ROOM_SCHEMA || !Array.isArray(data.items) || data.items.length > 20) throw new Error('Invalid room state');
  const seen = new Set();
  return data.items.map(item => {
    if (!Number.isSafeInteger(item.id) || item.id < 1 || seen.has(item.id) ||
        !allowedIds.has(item.blueprintId) || !Number.isFinite(item.x) || !Number.isFinite(item.y) ||
        item.x < 0 || item.x > 1 || item.y < 0 || item.y > 1 || typeof item.visible !== 'boolean') {
      throw new Error('Invalid room object');
    }
    seen.add(item.id);
    return {id:item.id, blueprintId:item.blueprintId, x:item.x*width, y:item.y*height, visible:item.visible};
  });
}
