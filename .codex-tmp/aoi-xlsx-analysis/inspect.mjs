import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath =
  "D:\\文档\\试飞院项目\\statisAOI__0729164525_兴趣区统计(1).xlsx";
const previewDir =
  "D:\\codes\\F18-Radar\\.codex-tmp\\aoi-xlsx-analysis\\previews";

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);

if (process.argv.includes("--geometry-only")) {
  const geometryObjectsOnly = await workbook.inspect({
    kind: "definedName,drawing",
    maxChars: 12000,
  });
  console.log("GEOMETRY_OBJECTS");
  console.log(geometryObjectsOnly.ndjson);

  const geometryTermsOnly = await workbook.inspect({
    kind: "match",
    searchTerm:
      "coordinate|coordinates|坐标|width|height|rectangle|rect|\\bx\\b|\\by\\b",
    options: { useRegex: true, maxResults: 200 },
    maxChars: 12000,
  });
  console.log("GEOMETRY_TERMS");
  console.log(geometryTermsOnly.ndjson);
  process.exit(0);
}

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 12,
  tableMaxCols: 24,
  tableMaxCellChars: 160,
});
console.log("OVERVIEW");
console.log(overview.ndjson);

const sheetIndex = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 6000,
});
console.log("SHEETS");
console.log(sheetIndex.ndjson);

const geometryObjects = await workbook.inspect({
  kind: "definedName,drawing",
  maxChars: 12000,
});
console.log("GEOMETRY_OBJECTS");
console.log(geometryObjects.ndjson);

const geometryTerms = await workbook.inspect({
  kind: "match",
  searchTerm:
    "coordinate|coordinates|坐标|width|height|rectangle|rect|\\bx\\b|\\by\\b",
  options: { useRegex: true, maxResults: 200 },
  maxChars: 12000,
});
console.log("GEOMETRY_TERMS");
console.log(geometryTerms.ndjson);

const sheetRecords = sheetIndex.ndjson
  .split(/\r?\n/)
  .filter(Boolean)
  .map((line) => JSON.parse(line))
  .filter((record) => record.name);

await fs.mkdir(previewDir, { recursive: true });
for (const [index, record] of sheetRecords.entries()) {
  const sheetName = record.name;
  const table = await workbook.inspect({
    kind: "table",
    sheetId: sheetName,
    maxChars: 30000,
    tableMaxRows: 200,
    tableMaxCols: 40,
    tableMaxCellChars: 200,
  });
  console.log(`TABLE:${sheetName}`);
  console.log(table.ndjson);

  const formulas = await workbook.inspect({
    kind: "formula",
    sheetId: sheetName,
    maxChars: 8000,
    options: { maxResults: 200 },
  });
  console.log(`FORMULAS:${sheetName}`);
  console.log(formulas.ndjson);

  const preview = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1.5,
    format: "png",
  });
  const safeName = sheetName.replace(/[<>:"/\\|?*]/g, "_");
  await fs.writeFile(
    `${previewDir}\\${String(index + 1).padStart(2, "0")}-${safeName}.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}
