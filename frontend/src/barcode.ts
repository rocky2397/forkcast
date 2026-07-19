/** On-device barcode reading, free on every browser (D9).
 *
 * Chrome/Android: the native BarcodeDetector API, zero dependencies.
 * Safari/iOS (no BarcodeDetector): zxing WASM, code-split so it only
 * downloads on first scan, self-hosted so the PWA works offline.
 */

import wasmUrl from "zxing-wasm/reader/zxing_reader.wasm?url";

const NATIVE_FORMATS = ["ean_13", "ean_8", "upc_a", "upc_e"];
const ZXING_FORMATS = ["EAN-13", "EAN-8", "UPC-A", "UPC-E"] as const;

async function nativeDetect(file: File): Promise<string | null> {
  const BD = (window as unknown as { BarcodeDetector?: any }).BarcodeDetector;
  if (!BD) return null;
  try {
    const supported: string[] = await BD.getSupportedFormats();
    const formats = NATIVE_FORMATS.filter((f) => supported.includes(f));
    if (formats.length === 0) return null;
    const bitmap = await createImageBitmap(file);
    const codes = await new BD({ formats }).detect(bitmap);
    return codes[0]?.rawValue ?? null;
  } catch {
    return null;
  }
}

async function wasmDetect(file: File): Promise<string | null> {
  const { prepareZXingModule, readBarcodes } = await import("zxing-wasm/reader");
  prepareZXingModule({
    overrides: {
      locateFile: (path: string) => (path.endsWith(".wasm") ? wasmUrl : path),
    },
  });
  const results = await readBarcodes(file, {
    formats: [...ZXING_FORMATS],
    maxNumberOfSymbols: 1,
  });
  return results[0]?.text || null;
}

export async function detectBarcode(file: File): Promise<string | null> {
  return (await nativeDetect(file)) ?? (await wasmDetect(file).catch(() => null));
}
