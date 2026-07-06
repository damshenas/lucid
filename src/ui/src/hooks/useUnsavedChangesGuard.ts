import { useEffect } from "react";

const DEFAULT_MESSAGE = "You have unsaved changes. Leave without saving?";

/**
 * Warns before the tab/window closes or reloads, and before following any in-app
 * link, while `dirty` is true.
 *
 * Intercepts capture-phase clicks on `<a>` elements (react-router's
 * `<NavLink>`/`<Link>` render as `<a>`) rather than hooking into react-router's
 * `useBlocker` — this app renders a plain `<BrowserRouter>`/`<Routes>` tree (see
 * main.tsx/App.tsx), not a data router (`createBrowserRouter`), so `useBlocker` isn't
 * available. Cancelling here simply suppresses the click before react-router (or the
 * browser, for a normal link) ever sees it.
 */
export function useUnsavedChangesGuard(dirty: boolean, message: string = DEFAULT_MESSAGE): void {
  useEffect(() => {
    if (!dirty) return;

    function onBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      e.returnValue = "";
    }

    function onClickCapture(e: MouseEvent) {
      const target = e.target as HTMLElement | null;
      const anchor = target?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!anchor) return;
      const url = new URL(anchor.href, window.location.href);
      if (url.origin !== window.location.origin) return; // external link — not our concern
      if (url.pathname === window.location.pathname) return; // same page (e.g. hash link)
      if (!window.confirm(message)) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    }

    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("click", onClickCapture, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("click", onClickCapture, true);
    };
  }, [dirty, message]);
}
