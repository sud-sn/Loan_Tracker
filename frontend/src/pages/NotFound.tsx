import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  const { t } = useTranslation();
  return (
    <div className="space-y-4 py-10 text-center">
      <p className="text-lg">{t("app.notFound")}</p>
      <Link to="/"><Button>{t("app.goHome")}</Button></Link>
    </div>
  );
}
