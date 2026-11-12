import { useState } from 'react'
import type { VaultItem, CardData, IdentityData, LoginData, NoteData } from '../types'
import {
  EyeIcon,
  EyeOffIcon,
  CopyIcon,
  CheckIcon,
  CreditCardIcon,
  UserIcon,
  KeyIcon,
  NoteIcon,
  StarIcon,
  ShieldIcon,
} from './Icons'

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        navigator.clipboard.writeText(value).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
      title="Copy to clipboard"
    >
      {copied ? (
        <CheckIcon className="w-3.5 h-3.5 text-green-500" />
      ) : (
        <CopyIcon className="w-3.5 h-3.5" />
      )}
    </button>
  )
}

interface FieldProps {
  label: string
  value: string
  masked?: boolean
  mono?: boolean
}

function Field({ label, value, masked = false, mono = false }: FieldProps) {
  const [revealed, setRevealed] = useState(false)
  if (!value) return null
  const display = masked && !revealed ? '••••••••' : value

  return (
    <div className="py-3 border-b border-slate-100 last:border-0">
      <div className="text-xs font-medium text-slate-500 mb-1">{label}</div>
      <div className="flex items-center gap-1">
        <span
          className={`text-sm text-slate-800 flex-1 break-all ${mono ? 'font-mono tracking-wider' : ''}`}
        >
          {display}
        </span>
        {masked && (
          <button
            onClick={() => setRevealed(r => !r)}
            className="p-1 rounded text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors flex-shrink-0"
            title={revealed ? 'Hide' : 'Reveal'}
          >
            {revealed ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        )}
        <CopyButton value={value} />
      </div>
    </div>
  )
}

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="pt-5 pb-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">
      {title}
    </div>
  )
}

function CardDetail({ card }: { card: CardData }) {
  return (
    <>
      <Field label="Cardholder Name" value={card.cardholderName} />
      <Field label="Card Number" value={card.number} masked mono />
      <Field label="Expiration Date" value={`${card.expMonth}/${card.expYear}`} />
      <Field label="Security Code (CVV)" value={card.code} masked />
      {card.billingAddress && (
        <>
          <SectionHeader title="Billing Address" />
          <Field label="Address" value={card.billingAddress.address1} />
          {card.billingAddress.address2 && (
            <Field label="Address 2" value={card.billingAddress.address2} />
          )}
          <Field label="City" value={card.billingAddress.city} />
          <Field label="State / Province" value={card.billingAddress.state} />
          <Field label="Postal Code" value={card.billingAddress.postalCode} />
          <Field label="Country" value={card.billingAddress.country} />
        </>
      )}
    </>
  )
}

function IdentityDetail({ identity }: { identity: IdentityData }) {
  const fullName = [identity.title, identity.firstName, identity.lastName]
    .filter(Boolean)
    .join(' ')
  return (
    <>
      <Field label="Full Name" value={fullName} />
      <Field label="Email" value={identity.email} />
      <Field label="Phone" value={identity.phone} />
      {identity.company && <Field label="Company" value={identity.company} />}
      {(identity.address1 || identity.city) && (
        <>
          <SectionHeader title="Address" />
          {identity.address1 && <Field label="Address" value={identity.address1} />}
          {identity.address2 && <Field label="Address 2" value={identity.address2} />}
          <Field label="City" value={identity.city} />
          <Field label="State / Province" value={identity.state} />
          <Field label="Postal Code" value={identity.postalCode} />
          <Field label="Country" value={identity.country} />
        </>
      )}
      {(identity.passportNumber || identity.dateOfBirth) && (
        <>
          <SectionHeader title="Travel Documents" />
          {identity.passportNumber && (
            <Field label="Passport Number" value={identity.passportNumber} masked />
          )}
          {identity.dateOfBirth && <Field label="Date of Birth" value={identity.dateOfBirth} />}
        </>
      )}
    </>
  )
}

function LoginDetail({ login }: { login: LoginData }) {
  return (
    <>
      <Field label="Username" value={login.username} />
      <Field label="Password" value={login.password} masked />
      {login.uris.map((uri, i) => (
        <Field
          key={i}
          label={login.uris.length > 1 ? `URL ${i + 1}` : 'URL'}
          value={uri}
        />
      ))}
    </>
  )
}

function NoteDetail({ note }: { note: NoteData }) {
  return (
    <div className="bg-slate-50 rounded-lg p-4 text-sm text-slate-700 whitespace-pre-wrap font-mono leading-relaxed">
      {note.content}
    </div>
  )
}

function ItemTypeIcon({ item }: { item: VaultItem }) {
  const base = 'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0'
  if (item.type === 'card')
    return (
      <div className={`${base} bg-blue-100 text-blue-600`}>
        <CreditCardIcon className="w-5 h-5" />
      </div>
    )
  if (item.type === 'identity')
    return (
      <div className={`${base} bg-violet-100 text-violet-600`}>
        <UserIcon className="w-5 h-5" />
      </div>
    )
  if (item.type === 'login')
    return (
      <div className={`${base} bg-amber-100 text-amber-600`}>
        <KeyIcon className="w-5 h-5" />
      </div>
    )
  return (
    <div className={`${base} bg-slate-100 text-slate-500`}>
      <NoteIcon className="w-5 h-5" />
    </div>
  )
}

const TYPE_LABELS: Record<string, string> = {
  card: 'Payment Card',
  identity: 'Identity',
  login: 'Login',
  note: 'Secure Note',
}

interface ItemDetailProps {
  item: VaultItem | null
}

export default function ItemDetail({ item }: ItemDetailProps) {
  if (!item) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50">
        <div className="text-center text-slate-400">
          <ShieldIcon className="w-16 h-16 mx-auto mb-3 opacity-20" />
          <p className="text-sm">Select an item to view details</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto bg-white">
      <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-center gap-3">
        <ItemTypeIcon item={item} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="font-semibold text-slate-800 text-base truncate">{item.name}</h2>
            {item.favorite && <StarIcon className="w-4 h-4 text-amber-400 flex-shrink-0" />}
          </div>
          <p className="text-xs text-slate-500">{TYPE_LABELS[item.type] ?? item.type}</p>
        </div>
      </div>

      <div className="px-6 py-4">
        {item.type === 'card' && item.card && <CardDetail card={item.card} />}
        {item.type === 'identity' && item.identity && <IdentityDetail identity={item.identity} />}
        {item.type === 'login' && item.login && <LoginDetail login={item.login} />}
        {item.type === 'note' && item.note && <NoteDetail note={item.note} />}

        {item.notes && (
          <div className="mt-4 pt-4 border-t border-slate-100">
            <div className="text-xs font-medium text-slate-500 mb-2">Notes</div>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{item.notes}</p>
          </div>
        )}

        <div className="mt-6 pt-4 border-t border-slate-100 space-y-1">
          <div className="text-xs text-slate-400">
            Created{' '}
            {new Date(item.createdAt).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </div>
          <div className="text-xs text-slate-400">
            Updated{' '}
            {new Date(item.updatedAt).toLocaleDateString('en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
