import { Avatar } from "@/components/ui/avatar";
import { BeeMark } from "@/components/ui/icons";

export type Message = { id: string; from: "me" | "agent"; text: string };
type Props = { message: Message; senderId: string; senderName: string };

/** One bubble with its sender: members get their own colour, the game master is honey. */
export function ChatMessage({ message, senderId, senderName }: Props) {
  const mine = message.from === "me";
  return (
    <li className={`rise flex items-end gap-2.5 ${mine ? "flex-row-reverse" : ""}`}>
      {mine ? (
        <Avatar id={senderId} name={senderName} size="sm" />
      ) : (
        <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-honey-soft">
          <BeeMark />
        </span>
      )}
      <div
        className={`flex max-w-[82%] flex-col gap-0.5 ${mine ? "items-end" : "items-start"}`}
      >
        <span className="px-1 text-xs font-semibold text-muted">{senderName}</span>
        <p
          className={`rounded-2xl px-4 py-2.5 leading-relaxed break-words whitespace-pre-wrap ${
            mine
              ? "rounded-br-md bg-accent text-paper"
              : "rounded-bl-md border border-honey-deep/40 bg-honey-soft font-display"
          }`}
        >
          {message.text}
        </p>
      </div>
    </li>
  );
}
