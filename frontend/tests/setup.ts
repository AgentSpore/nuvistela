import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom has no modal <dialog>: stand in for showModal/close and the Escape key.
const dialog = HTMLDialogElement.prototype;
if (!dialog.showModal) {
  dialog.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const cancel = new Event("cancel", { cancelable: true });
      this.dispatchEvent(cancel);
      if (!cancel.defaultPrevented) this.close();
    };
    document.addEventListener("keydown", onKey);
    this.addEventListener("close", () => document.removeEventListener("keydown", onKey));
  };
  dialog.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
}
