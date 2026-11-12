export type ItemType = 'login' | 'card' | 'identity' | 'note'

export type NavCategory = 'all' | 'favorites' | ItemType

export interface BillingAddress {
  address1: string
  address2: string
  city: string
  state: string
  postalCode: string
  country: string
}

export interface CardData {
  cardholderName: string
  brand: string
  number: string
  expMonth: string
  expYear: string
  code: string
  billingAddress?: BillingAddress
}

export interface IdentityData {
  title: string
  firstName: string
  lastName: string
  email: string
  phone: string
  company: string
  address1: string
  address2: string
  city: string
  state: string
  postalCode: string
  country: string
  passportNumber: string
  dateOfBirth: string
}

export interface LoginData {
  username: string
  password: string
  uris: string[]
}

export interface NoteData {
  content: string
}

export interface VaultItem {
  id: string
  name: string
  type: ItemType
  favorite: boolean
  notes?: string
  card?: CardData
  identity?: IdentityData
  login?: LoginData
  note?: NoteData
  createdAt: string
  updatedAt: string
}

export type VaultItemCreate = Omit<VaultItem, 'id' | 'createdAt' | 'updatedAt'>

export interface User {
  id: string
  username: string
}
