// Ports app.py's FILE_ICONS / STATUS_COLORS / _file_type constants verbatim.
export const FILE_ICONS: Record<string, string> = {
  pdf: "📕",
  docx: "📘",
  txt: "📄",
  png: "🖼️",
  jpg: "🖼️",
  jpeg: "🖼️",
};

export const STATUS_COLORS: Record<string, string> = {
  processing: "#FECB52",
  processed: "#00CC96",
  failed: "#EF553B",
};

export function fileType(docName: string): string {
  const parts = docName.split(".");
  return parts.length > 1 ? parts[parts.length - 1].toLowerCase() : "file";
}

export function fileIcon(docName: string): string {
  return FILE_ICONS[fileType(docName)] ?? "📁";
}
