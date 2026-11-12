"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft, Globe, Phone, MapPin, Users, Handshake } from "lucide-react";
import { formatCurrency } from "@/lib/utils";
import Link from "next/link";

export default function CompanyDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const [company, setCompany] = useState<any>(null);
  const [contacts, setContacts] = useState<any[]>([]);
  const [deals, setDeals] = useState<any[]>([]);

  useEffect(() => {
    fetch(`/api/companies/${id}`).then((r) => r.ok && r.json()).then(setCompany);
    fetch(`/api/contacts?companyId=${id}&limit=100`).then((r) => r.ok && r.json()).then((d) => setContacts(d?.data || []));
    fetch(`/api/deals`).then((r) => r.ok && r.json()).then((d) =>
      setDeals((d || []).filter((deal: any) => deal.companyId === parseInt(id as string)))
    );
  }, [id]);

  if (!company) return <div>Loading...</div>;

  return (
    <div className="max-w-4xl">
      <Button variant="ghost" size="sm" onClick={() => router.back()} className="mb-4">
        <ArrowLeft className="h-4 w-4 mr-2" />
        Back
      </Button>

      <h1 className="text-2xl font-bold mb-6">{company.name}</h1>

      <Card className="mb-6">
        <CardContent className="pt-6 space-y-3">
          {company.domain && (
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 text-muted-foreground" />
              <span>{company.domain}</span>
            </div>
          )}
          {company.phone && (
            <div className="flex items-center gap-2">
              <Phone className="h-4 w-4 text-muted-foreground" />
              <span>{company.phone}</span>
            </div>
          )}
          {company.address && (
            <div className="flex items-center gap-2">
              <MapPin className="h-4 w-4 text-muted-foreground" />
              <span>{company.address}</span>
            </div>
          )}
          {company.notes && (
            <p className="text-sm text-muted-foreground">{company.notes}</p>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4" />
              Contacts ({contacts.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {contacts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No contacts</p>
            ) : (
              <div className="space-y-2">
                {contacts.map((c: any) => (
                  <Link
                    key={c.id}
                    href={`/contacts/${c.id}`}
                    className="block p-2 rounded hover:bg-muted"
                  >
                    <p className="text-sm font-medium">{c.firstName} {c.lastName}</p>
                    <p className="text-xs text-muted-foreground">{c.jobTitle || c.email}</p>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Handshake className="h-4 w-4" />
              Deals ({deals.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {deals.length === 0 ? (
              <p className="text-sm text-muted-foreground">No deals</p>
            ) : (
              <div className="space-y-2">
                {deals.map((d: any) => (
                  <Link
                    key={d.id}
                    href={`/deals/${d.id}`}
                    className="flex items-center justify-between p-2 rounded hover:bg-muted"
                  >
                    <div>
                      <p className="text-sm font-medium">{d.title}</p>
                      <p className="text-xs text-muted-foreground">{d.stageName}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-semibold">{formatCurrency(d.value)}</p>
                      <Badge variant="outline" className="text-xs">{d.status}</Badge>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
