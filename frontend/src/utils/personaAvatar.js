// Face for a persona that matches its real race, gender and age.
// DiceBear picks from each option list using the name as seed, so the same
// persona always gets the same face. Missing fields fall back to the defaults.
import { createAvatar } from '@dicebear/core'
import { avataaars } from '@dicebear/collection'

const SKIN = {
  'African/Black': ['614335', 'ae5d29'],
  'Coloured': ['d08b5b', 'ae5d29'],
  'Indian/Asian': ['d08b5b', 'edb98a'],
  'White': ['ffdbb4', 'edb98a'],
}
const DARK_HAIR = ['2c1b18', '4a312c', '724133']
const HAIR = {
  'African/Black': DARK_HAIR,
  'Coloured': DARK_HAIR,
  'Indian/Asian': ['2c1b18', '4a312c'],
  'White': ['2c1b18', '4a312c', '724133', 'a55728', 'b58143', 'd6b370'],
}
const GREY_HAIR = ['e8e1e1', 'ecdcbf']
const TOP = {
  female: ['bob', 'bun', 'curly', 'curvy', 'bigHair', 'frida', 'fro', 'froBand',
    'longButNotTooLong', 'miaWallace', 'straight01', 'straight02', 'straightAndStrand', 'dreads'],
  male: ['shortCurly', 'shortFlat', 'shortRound', 'shortWaved', 'sides',
    'theCaesar', 'theCaesarAndSidePart', 'dreads01', 'frizzle', 'shaggy'],
}

const _cache = new Map()

export const personaAvatar = (p = {}) => {
  const seed = p.name || p.agent_name || String(p.id ?? 'unknown')
  const race = p.race || ''
  const gender = String(p.gender || '').toLowerCase()
  const age = Number(p.age) || null
  const key = `${seed}|${race}|${gender}|${age}`
  if (_cache.has(key)) return _cache.get(key)

  const opts = {
    seed, radius: 50,
    backgroundColor: ['b6e3f4', 'c0e8d5', 'fde68a', 'ffd6a5'],
    backgroundType: ['solid'],
  }
  if (SKIN[race]) opts.skinColor = SKIN[race]
  const sex = gender.startsWith('f') ? 'female' : gender.startsWith('m') ? 'male' : null
  if (sex) {
    opts.top = TOP[sex]
    opts.topProbability = 100
    opts.facialHairProbability = sex === 'male' && age >= 25 ? 40 : 0
  }
  if (age >= 60) {
    opts.hairColor = GREY_HAIR
    opts.facialHairColor = GREY_HAIR
    opts.accessories = ['prescription01', 'prescription02', 'round']
    opts.accessoriesProbability = 60
  } else {
    if (HAIR[race]) { opts.hairColor = HAIR[race]; opts.facialHairColor = HAIR[race] }
    opts.accessoriesProbability = age >= 45 ? 25 : 5
    opts.accessories = ['prescription01', 'prescription02', 'round', 'wayfarers']
  }

  const uri = `data:image/svg+xml;utf8,${encodeURIComponent(createAvatar(avataaars, opts).toString())}`
  _cache.set(key, uri)
  return uri
}
