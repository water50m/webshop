import DraftOrderDetailClient from "./DraftOrderDetailClient";

// Capacitor's static bundle needs one route shell. The page itself is a client
// component and loads the actual order id from the API after navigation.
export function generateStaticParams() {
  return [{ id: "0" }];
}

export default function DraftOrderDetailPage() {
  return <DraftOrderDetailClient />;
}
