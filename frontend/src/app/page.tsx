import { redirect } from "next/navigation";
import { applicationRoutes } from "@/utils/applicationRoutes";

export default function Home() {
  redirect(applicationRoutes.login);
}
