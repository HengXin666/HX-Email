import React, { useEffect, useState } from "react";
import { IconServer } from "../../components/icons";
import { getPlatformBrand } from "./platform_catalog";

type PlatformLogoSize = "xs" | "sm" | "md" | "lg";

interface PlatformLogoProps {
  name: string;
  size?: PlatformLogoSize;
  className?: string;
}

const SIZE_CLASSES: Record<PlatformLogoSize, string> = {
  xs: "w-6 h-6 rounded-md",
  sm: "w-8 h-8 rounded-md",
  md: "w-10 h-10 rounded-lg",
  lg: "w-14 h-14 rounded-xl",
};

const TEXT_CLASSES: Record<PlatformLogoSize, string> = {
  xs: "text-[9px]",
  sm: "text-[10px]",
  md: "text-xs",
  lg: "text-sm",
};

const ICON_SIZES: Record<PlatformLogoSize, number> = {
  xs: 12,
  sm: 14,
  md: 18,
  lg: 24,
};

export const PlatformLogo: React.FC<PlatformLogoProps> = ({
  name,
  size = "md",
  className = "",
}) => {
  const brand = getPlatformBrand(name);
  const [hasLogoError, setHasLogoError] = useState(false);
  const logoUrl = hasLogoError ? null : brand.logoUrl;

  useEffect(() => {
    setHasLogoError(false);
  }, [brand.logoUrl]);

  return (
    <div
      className={`${SIZE_CLASSES[size]} border flex items-center justify-center shrink-0 overflow-hidden ${className}`}
      style={{
        backgroundColor: brand.backgroundColor,
        borderColor: `${brand.accentColor}55`,
        color: brand.accentColor,
      }}
      title={brand.label}
    >
      {logoUrl ? (
        <img
          src={logoUrl}
          alt=""
          aria-hidden="true"
          className="w-[72%] h-[72%] object-contain"
          onError={() => setHasLogoError(true)}
        />
      ) : brand.fallbackText !== "?" ? (
        <span className={`${TEXT_CLASSES[size]} font-semibold leading-none`}>
          {brand.fallbackText}
        </span>
      ) : (
        <IconServer size={ICON_SIZES[size]} />
      )}
    </div>
  );
};
