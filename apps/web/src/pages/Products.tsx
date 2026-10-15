import { FormEvent, useEffect, useState } from "react";
import { api, Product, ProductPlacement } from "../api";

export default function Products() {
  const [products, setProducts] = useState<Product[]>([]);
  const [placements, setPlacements] = useState<ProductPlacement[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [brand, setBrand] = useState("");
  const [description, setDescription] = useState("");
  const [productKind, setProductKind] = useState<"product" | "garment">("product");
  const [garment, setGarment] = useState({
    category: "",
    color: "",
    material: "",
    pattern: "",
    fit: "",
    sleeves: "",
    neckline: "",
    length: "",
    details: "",
  });
  const [file, setFile] = useState<File | null>(null);

  async function refresh() {
    const [p, pl] = await Promise.all([api.listProducts(), api.productPlacements()]);
    setProducts(p);
    setPlacements(pl.placements);
  }

  useEffect(() => {
    refresh().catch((e) => setError(e.message));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Choose a product image (PNG/JPEG/WebP).");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await api.createProduct({
        name,
        brand: brand || undefined,
        description: description || undefined,
        productKind,
        garment: productKind === "garment" ? garment : undefined,
        image: file,
      });
      setName("");
      setBrand("");
      setDescription("");
      setProductKind("product");
      setGarment({
        category: "",
        color: "",
        material: "",
        pattern: "",
        fit: "",
        sleeves: "",
        neckline: "",
        length: "",
        details: "",
      });
      setFile(null);
      setInfo("Product added. Attach it from Character Studio → Batch stills.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Delete this product and its image files?")) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteProduct(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl tracking-tight">Products</h1>
        <p className="mt-2 max-w-2xl text-sm text-slate-400">
          Upload packaging or product shots to use as optional references when generating ad-style
          stills. This is separate from character face refs — product images are for commercial
          placement in the batch brief.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-100">
          {error}
        </div>
      )}
      {info && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
          {info}
        </div>
      )}

      <section className="card space-y-4 p-5">
        <h2 className="font-display text-xl">Add product</h2>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => void onSubmit(e)}>
          <label className="block space-y-1 text-sm">
            <span className="text-slate-400">Name</span>
            <input
              className="input"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Aurora Serum 30ml"
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-slate-400">Brand (optional)</span>
            <input
              className="input"
              value={brand}
              onChange={(e) => setBrand(e.target.value)}
              placeholder="Aurora"
            />
          </label>
          <label className="block space-y-1 text-sm sm:col-span-2">
            <span className="text-slate-400">Description (optional)</span>
            <input
              className="input"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="matte frosted glass bottle, gold dropper, sage label"
            />
          </label>
          <label className="block space-y-1 text-sm">
            <span className="text-slate-400">Type</span>
            <select
              className="input"
              value={productKind}
              onChange={(e) => setProductKind(e.target.value as "product" | "garment")}
            >
              <option value="product">General product</option>
              <option value="garment">Clothing / garment</option>
            </select>
          </label>
          {productKind === "garment" && (
            <div className="grid gap-3 sm:col-span-2 sm:grid-cols-3">
              {(
                [
                  ["category", "Category", "dress, jacket, top"],
                  ["color", "Color", "deep burgundy"],
                  ["material", "Material", "silk, denim, knit"],
                  ["pattern", "Pattern", "solid, floral, striped"],
                  ["fit", "Fit", "fitted, relaxed, oversized"],
                  ["sleeves", "Sleeves", "sleeveless, long sleeve"],
                  ["neckline", "Neckline", "crew, V-neck, halter"],
                  ["length", "Length", "cropped, midi, ankle"],
                  ["details", "Exact details", "buttons, logo, trim, seams"],
                ] as const
              ).map(([key, label, placeholder]) => (
                <label key={key} className="block space-y-1 text-sm">
                  <span className="text-slate-400">{label}</span>
                  <input
                    className="input"
                    required={key === "category"}
                    value={garment[key]}
                    placeholder={placeholder}
                    onChange={(e) =>
                      setGarment((current) => ({ ...current, [key]: e.target.value }))
                    }
                  />
                </label>
              ))}
            </div>
          )}
          <label className="block space-y-1 text-sm sm:col-span-2">
            <span className="text-slate-400">Product image</span>
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              className="block w-full text-sm text-slate-300 file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-slate-100"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
          </label>
          <div className="sm:col-span-2">
            <button type="submit" className="btn-primary" disabled={busy}>
              Upload product
            </button>
          </div>
        </form>
        {placements.length > 0 && (
          <p className="text-xs text-slate-500">
            Studio placements: {placements.map((p) => p.label).join(", ")}.
          </p>
        )}
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="font-display text-xl">Library ({products.length})</h2>
        {products.length === 0 ? (
          <p className="text-sm text-slate-500">No products yet.</p>
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {products.map((p) => (
              <li key={p.id} className="overflow-hidden rounded-xl bg-white/5">
                <div className="aspect-square bg-black/30">
                  {p.thumb_path || p.primary_path ? (
                    <img
                      src={api.mediaUrl(p.thumb_path || p.primary_path)}
                      alt={p.name}
                      className="h-full w-full object-contain p-3"
                    />
                  ) : null}
                </div>
                <div className="space-y-1 p-3">
                  <div className="font-medium text-slate-100">{p.name}</div>
                  {p.meta?.product_kind === "garment" && (
                    <div className="text-xs font-medium text-accent-soft">garment</div>
                  )}
                  {p.brand && <div className="text-xs text-slate-500">{p.brand}</div>}
                  {p.description && (
                    <p className="line-clamp-2 text-xs text-slate-400">{p.description}</p>
                  )}
                  <button
                    type="button"
                    className="btn-ghost mt-2 text-xs text-rose-200"
                    disabled={busy}
                    onClick={() => void remove(p.id)}
                  >
                    Delete product
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
