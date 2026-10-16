import { useEffect, useState } from "react";

/** Định tuyến băm: /c/#/vi-the?x=1. Không cần cấu hình nginx cho đường dẫn con. */
const parse = () => {
  const raw = (location.hash || "").replace(/^#/, "") || "/hom-nay";
  const [path, qs] = raw.split("?");
  return { path: path.startsWith("/") ? path : `/${path}`, query: Object.fromEntries(new URLSearchParams(qs || "")) };
};

export function useRoute() {
  const [r, setR] = useState(parse);
  useEffect(() => {
    const h = () => { setR(parse()); window.scrollTo({ top: 0 }); };
    addEventListener("hashchange", h);
    return () => removeEventListener("hashchange", h);
  }, []);
  return r;
}

export const go = (path) => { location.hash = `#${path}`; };
