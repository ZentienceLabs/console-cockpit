import React, { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { getProxyBaseUrl, getGlobalLitellmHeaderName } from "@/components/networking";

interface ThemeContextType {
  logoUrl: string | null;
  setLogoUrl: (url: string | null) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
};

interface ThemeProviderProps {
  children: ReactNode;
  accessToken?: string | null;
}

export const ThemeProvider: React.FC<ThemeProviderProps> = ({ children, accessToken }) => {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);

  // Load per-account theme when logged in, else load global theme
  useEffect(() => {
    const loadTheme = async () => {
      try {
        const proxyBaseUrl = getProxyBaseUrl();

        if (accessToken) {
          // Logged in: fetch per-account theme (falls back to global on backend)
          const url = proxyBaseUrl ? `${proxyBaseUrl}/account/theme` : "/account/theme";
          const response = await fetch(url, {
            method: "GET",
            headers: {
              [getGlobalLitellmHeaderName()]: `Bearer ${accessToken}`,
              "Content-Type": "application/json",
            },
          });

          if (response.ok) {
            const data = await response.json();
            if (data.values?.logo_url) {
              setLogoUrl(data.values.logo_url);
              return;
            }
          }
        }

        // Not logged in or no account theme: load global theme
        const url = proxyBaseUrl
          ? `${proxyBaseUrl}/get/ui_theme_settings`
          : "/get/ui_theme_settings";
        const response = await fetch(url, {
          method: "GET",
          headers: { "Content-Type": "application/json" },
        });

        if (response.ok) {
          const data = await response.json();
          if (data.values?.logo_url) {
            setLogoUrl(data.values.logo_url);
          }
        }
      } catch (error) {
        console.warn("Failed to load logo settings from backend:", error);
      }
    };

    loadTheme();
  }, [accessToken]);

  return <ThemeContext.Provider value={{ logoUrl, setLogoUrl }}>{children}</ThemeContext.Provider>;
};
