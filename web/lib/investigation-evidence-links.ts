export function safeOfficialUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url.href : undefined;
  } catch { return undefined; }
}

export function materialPath(taskId: string, artifactId: string): string {
  return `/review/investigations/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(artifactId)}`;
}

export function materialName(material: { artifact_id: string; remote_path?: string }): string {
  return material.remote_path?.split(/[\\/]/).filter(Boolean).at(-1) || material.artifact_id;
}
