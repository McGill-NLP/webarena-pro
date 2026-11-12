import { PrismaClient } from "@prisma/client";
import { resetDatabase } from "../lib/seed";

const prisma = new PrismaClient();

async function main() {
  await resetDatabase(prisma);
}

main()
  .catch((error) => {
    console.error(error);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
