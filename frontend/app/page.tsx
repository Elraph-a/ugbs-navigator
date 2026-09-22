import { Conversation } from "@/components/Conversation";

/**
 * The conversation lives in component state, so navigating from "/" to "/"
 * would keep it. Keying on the query string gives "New enquiry" (?new=…) and
 * the sidebar's common enquiries (?q=…) a genuinely fresh conversation.
 */
export default async function AskPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const key = `${params.q ?? ""}|${params.new ?? ""}`;
  return <Conversation key={key} />;
}
