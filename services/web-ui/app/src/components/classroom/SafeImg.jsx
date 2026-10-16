// Ảnh có dự phòng: nếu tệp mất (404) thì hiện khung "Ảnh không còn" thay vì biểu tượng ảnh vỡ.
import { useState } from "react";

export default function SafeImg({ src, alt = "", className, lang = "vi", ...rest }) {
  const [bad, setBad] = useState(false);
  if (bad) return <span className={`cr-imgmiss ${className || ""}`} role="img" aria-label={alt || undefined}>{lang === "en" ? "Image no longer available" : "Ảnh không còn"}</span>;
  return <img src={src} alt={alt} className={className} onError={() => setBad(true)} {...rest} />;
}
