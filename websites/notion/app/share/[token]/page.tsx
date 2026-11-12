import { prisma } from "@/lib/prisma";

export default async function SharedPage({ params }: { params: { token: string } }) {
  const shareLink = await prisma.shareLink.findUnique({
    where: { token: params.token },
    include: {
      page: {
        include: {
          blocks: { orderBy: { position: "asc" } },
          database: {
            include: {
              properties: { orderBy: { position: "asc" } },
              rows: { orderBy: { position: "asc" }, include: { cells: true } },
            },
          },
        },
      },
    },
  });

  const expired = shareLink?.expiresAt ? shareLink.expiresAt.getTime() < Date.now() : false;

  if (!shareLink || !shareLink.isActive || expired) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#ffffff] px-6">
        <div className="w-full max-w-xl rounded-xl border border-[#ebebeb] bg-white p-8">
          <h1 className="text-2xl font-semibold text-[#111]">This shared link is not available</h1>
        </div>
      </div>
    );
  }

  const page = shareLink.page;
  const database = page.database;

  return (
    <div className="min-h-screen bg-[#ffffff] text-[#191919]">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <p className="mb-2 text-xs uppercase tracking-[0.16em] text-[#888]">Shared page</p>
        <h1 className="mb-8 text-4xl font-semibold tracking-[-0.01em]">{page.title}</h1>

        {page.type === "database" && database ? (
          <div className="overflow-auto rounded-lg border border-[#ebebeb]">
            <table className="min-w-full text-sm">
              <thead className="bg-[#fafafa]">
                <tr>
                  {database.properties.map((property) => (
                    <th key={property.id} className="px-3 py-2 text-left text-xs font-medium uppercase tracking-[0.08em] text-[#888]">
                      {property.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {database.rows.map((row) => (
                  <tr key={row.id} className="border-t border-[#f0f0f0]">
                    {database.properties.map((property) => {
                      const value =
                        property.type === "title"
                          ? row.title
                          : row.cells.find((cell) => cell.propertyId === property.id)?.valueJson;
                      return (
                        <td key={property.id} className="px-3 py-2 align-top">
                          {Array.isArray(value) ? value.join(", ") : String(value ?? "")}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="space-y-4">
            {page.blocks.map((block) => {
              if (block.type === "heading_1") {
                return <h2 key={block.id} className="text-3xl font-semibold tracking-[-0.01em]">{block.contentText}</h2>;
              }
              if (block.type === "heading_2") {
                return <h3 key={block.id} className="text-2xl font-semibold tracking-[-0.01em]">{block.contentText}</h3>;
              }
              if (block.type === "heading_3") {
                return <h4 key={block.id} className="text-xl font-semibold">{block.contentText}</h4>;
              }
              if (block.type === "todo") {
                return (
                  <label key={block.id} className="flex items-start gap-2 text-[15px] leading-7">
                    <input type="checkbox" checked={Boolean(block.checked)} readOnly className="mt-2" />
                    <span>{block.contentText}</span>
                  </label>
                );
              }
              if (block.type === "image") {
                return (
                  <figure key={block.id} className="space-y-2">
                    {block.imageUrl ? <img src={block.imageUrl} alt={block.contentText ?? "image"} className="max-h-[420px] w-full rounded-lg border border-[#ebebeb] object-contain" /> : null}
                    {block.contentText ? <figcaption className="text-sm text-[#777]">{block.contentText}</figcaption> : null}
                  </figure>
                );
              }
              if (block.type === "bulleted_list_item") {
                return <p key={block.id} className="text-[15px] leading-7">- {block.contentText}</p>;
              }
              if (block.type === "numbered_list_item") {
                return <p key={block.id} className="text-[15px] leading-7">1. {block.contentText}</p>;
              }
              if (block.type === "toggle") {
                return (
                  <details key={block.id} className="rounded-md border border-[#ebebeb] px-3 py-2 text-[15px]">
                    <summary className="cursor-pointer">{block.contentText || "Toggle"}</summary>
                  </details>
                );
              }
              return (
                <p key={block.id} className="text-[15px] leading-7 text-[#2f2f2f]">
                  {block.contentText}
                </p>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
