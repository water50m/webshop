"use client";

import { createContext, useContext } from "react";

export const MobileNavContext = createContext<(open: boolean) => void>(() => {});

export function useMobileNav() {
  return useContext(MobileNavContext);
}
