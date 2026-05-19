// 声音库（83 个，对齐 Soft Echo）
// 每个声音: { id, label, icon, src, defaultVolume }
import {
  // nature
  Waves, Wind, Trees, Flame, Droplet, Droplets, Footprints, Leaf,
  // rain
  CloudRain, Zap, Cloud, Car, Umbrella, Tent,
  // animals (lucide 缺很多，用语义最近的)
  Bird, Bug, Cat, Dog, Fish, PawPrint, Egg, Beef,
  // urban
  TrafficCone, Siren, Users, PartyPopper, Truck,
  // places
  Coffee, Plane, Church, Building, Building2, Hammer,
  Beer, MapPin, Briefcase, ShoppingBasket, ShoppingCart,
  Sparkles, FlaskConical, Shirt, UtensilsCrossed, Library,
  // transport
  TrainFront, TramFront, Sailboat, Ship, Anchor,
  // things
  Keyboard, FileText, Clock, Bell, Fan,
  Projector, FlaskRound, Disc, Radio, Music, Music2,
  Wrench, Wand,
  // noise
  Music3, Music4,
} from 'lucide-react';

export const SOUND_CATEGORIES = [
  {
    id: 'nature',
    label: '自然',
    sounds: [
      { id: 'river',          label: '河流',     icon: Waves,      src: '/sounds/nature/river.mp3' },
      { id: 'waves',          label: '海浪',     icon: Waves,      src: '/sounds/nature/waves.mp3' },
      { id: 'campfire',       label: '篝火',     icon: Flame,      src: '/sounds/nature/campfire.mp3' },
      { id: 'wind',           label: '风',       icon: Wind,       src: '/sounds/nature/wind.mp3' },
      { id: 'howling-wind',   label: '呼啸风',   icon: Wind,       src: '/sounds/nature/howling-wind.mp3' },
      { id: 'wind-in-trees',  label: '林间风',   icon: Trees,      src: '/sounds/nature/wind-in-trees.mp3' },
      { id: 'waterfall',      label: '瀑布',     icon: Droplets,   src: '/sounds/nature/waterfall.mp3' },
      { id: 'walk-in-snow',   label: '雪地行走', icon: Footprints, src: '/sounds/nature/walk-in-snow.mp3' },
      { id: 'walk-on-leaves', label: '落叶行走', icon: Leaf,       src: '/sounds/nature/walk-on-leaves.mp3' },
      { id: 'walk-on-gravel', label: '砾石行走', icon: Footprints, src: '/sounds/nature/walk-on-gravel.mp3' },
      { id: 'droplets',       label: '水滴',     icon: Droplet,    src: '/sounds/nature/droplets.mp3' },
      { id: 'jungle',         label: '丛林',     icon: Trees,      src: '/sounds/nature/jungle.mp3' },
    ],
  },
  {
    id: 'rain',
    label: '雨声',
    sounds: [
      { id: 'light-rain',       label: '小雨',     icon: CloudRain, src: '/sounds/rain/light-rain.mp3' },
      { id: 'heavy-rain',       label: '大雨',     icon: CloudRain, src: '/sounds/rain/heavy-rain.mp3' },
      { id: 'thunder',          label: '雷声',     icon: Zap,       src: '/sounds/rain/thunder.mp3' },
      { id: 'rain-on-window',   label: '雨打窗',   icon: Cloud,     src: '/sounds/rain/rain-on-window.mp3' },
      { id: 'rain-on-car-roof', label: '雨打车顶', icon: Car,       src: '/sounds/rain/rain-on-car-roof.mp3' },
      { id: 'rain-on-umbrella', label: '雨打伞',   icon: Umbrella,  src: '/sounds/rain/rain-on-umbrella.mp3' },
      { id: 'rain-on-tent',     label: '雨打帐篷', icon: Tent,      src: '/sounds/rain/rain-on-tent.mp3' },
      { id: 'rain-on-leaves',   label: '雨打叶',   icon: Leaf,      src: '/sounds/rain/rain-on-leaves.mp3' },
    ],
  },
  {
    id: 'animals',
    label: '动物',
    sounds: [
      { id: 'birds',        label: '鸟鸣',   icon: Bird,     src: '/sounds/animals/birds.mp3' },
      { id: 'seagulls',     label: '海鸥',   icon: Bird,     src: '/sounds/animals/seagulls.mp3' },
      { id: 'crickets',     label: '蟋蟀',   icon: Bug,      src: '/sounds/animals/crickets.mp3' },
      { id: 'wolf',         label: '狼嚎',   icon: Dog,      src: '/sounds/animals/wolf.mp3' },
      { id: 'owl',          label: '猫头鹰', icon: Bird,     src: '/sounds/animals/owl.mp3' },
      { id: 'frog',         label: '青蛙',   icon: PawPrint, src: '/sounds/animals/frog.mp3' },
      { id: 'dog-barking',  label: '狗叫',   icon: Dog,      src: '/sounds/animals/dog-barking.mp3' },
      { id: 'horse-galopp', label: '马蹄',   icon: PawPrint, src: '/sounds/animals/horse-galopp.mp3' },
      { id: 'cat-purring',  label: '猫呼噜', icon: Cat,      src: '/sounds/animals/cat-purring.mp3' },
      { id: 'crows',        label: '乌鸦',   icon: Bird,     src: '/sounds/animals/crows.mp3' },
      { id: 'whale',        label: '鲸鱼',   icon: Fish,     src: '/sounds/animals/whale.mp3' },
      { id: 'beehive',      label: '蜂巢',   icon: Bug,      src: '/sounds/animals/beehive.mp3' },
      { id: 'woodpecker',   label: '啄木鸟', icon: Bird,     src: '/sounds/animals/woodpecker.mp3' },
      { id: 'chickens',     label: '鸡',     icon: Egg,      src: '/sounds/animals/chickens.mp3' },
      { id: 'cows',         label: '奶牛',   icon: Beef,     src: '/sounds/animals/cows.mp3' },
      { id: 'sheep',        label: '羊',     icon: PawPrint, src: '/sounds/animals/sheep.mp3' },
    ],
  },
  {
    id: 'urban',
    label: '都市',
    sounds: [
      { id: 'highway',         label: '高速',   icon: Car,         src: '/sounds/urban/highway.mp3' },
      { id: 'road',            label: '马路',   icon: Truck,       src: '/sounds/urban/road.mp3' },
      { id: 'ambulance-siren', label: '警笛',   icon: Siren,       src: '/sounds/urban/ambulance-siren.mp3' },
      { id: 'busy-street',     label: '闹市',   icon: TrafficCone, src: '/sounds/urban/busy-street.mp3' },
      { id: 'crowd',           label: '人群',   icon: Users,       src: '/sounds/urban/crowd.mp3' },
      { id: 'traffic',         label: '车流',   icon: Car,         src: '/sounds/urban/traffic.mp3' },
      { id: 'fireworks',       label: '烟火',   icon: PartyPopper, src: '/sounds/urban/fireworks.mp3' },
    ],
  },
  {
    id: 'places',
    label: '场所',
    sounds: [
      { id: 'cafe',             label: '咖啡厅', icon: Coffee,           src: '/sounds/places/cafe.mp3' },
      { id: 'airport',          label: '机场',   icon: Plane,            src: '/sounds/places/airport.mp3' },
      { id: 'church',           label: '教堂',   icon: Church,           src: '/sounds/places/church.mp3' },
      { id: 'temple',           label: '寺庙',   icon: Building2,        src: '/sounds/places/temple.mp3' },
      { id: 'construction-site',label: '工地',   icon: Hammer,           src: '/sounds/places/construction-site.mp3' },
      { id: 'underwater',       label: '水下',   icon: Fish,             src: '/sounds/places/underwater.mp3' },
      { id: 'crowded-bar',      label: '酒吧',   icon: Beer,             src: '/sounds/places/crowded-bar.mp3' },
      { id: 'night-village',    label: '夜村',   icon: MapPin,           src: '/sounds/places/night-village.mp3' },
      { id: 'subway-station',   label: '地铁站', icon: TramFront,        src: '/sounds/places/subway-station.mp3' },
      { id: 'office',           label: '办公室', icon: Briefcase,        src: '/sounds/places/office.mp3' },
      { id: 'supermarket',      label: '超市',   icon: ShoppingCart,     src: '/sounds/places/supermarket.mp3' },
      { id: 'carousel',         label: '旋转木马', icon: Sparkles,       src: '/sounds/places/carousel.mp3' },
      { id: 'laboratory',       label: '实验室', icon: FlaskConical,     src: '/sounds/places/laboratory.mp3' },
      { id: 'laundry-room',     label: '洗衣房', icon: Shirt,            src: '/sounds/places/laundry-room.mp3' },
      { id: 'restaurant',       label: '餐厅',   icon: UtensilsCrossed,  src: '/sounds/places/restaurant.mp3' },
      { id: 'library',          label: '图书馆', icon: Library,          src: '/sounds/places/library.mp3' },
    ],
  },
  {
    id: 'transport',
    label: '交通',
    sounds: [
      { id: 'train',           label: '火车',   icon: TrainFront, src: '/sounds/transport/train.mp3' },
      { id: 'inside-a-train',  label: '车厢内', icon: TrainFront, src: '/sounds/transport/inside-a-train.mp3' },
      { id: 'airplane',        label: '飞机',   icon: Plane,      src: '/sounds/transport/airplane.mp3' },
      { id: 'submarine',       label: '潜艇',   icon: Ship,       src: '/sounds/transport/submarine.mp3' },
      { id: 'sailboat',        label: '帆船',   icon: Sailboat,   src: '/sounds/transport/sailboat.mp3' },
      { id: 'rowing-boat',     label: '划船',   icon: Anchor,     src: '/sounds/transport/rowing-boat.mp3' },
    ],
  },
  {
    id: 'things',
    label: '物件',
    sounds: [
      { id: 'keyboard',          label: '键盘',   icon: Keyboard,    src: '/sounds/things/keyboard.mp3' },
      { id: 'typewriter',        label: '打字机', icon: Keyboard,    src: '/sounds/things/typewriter.mp3' },
      { id: 'paper',             label: '纸张',   icon: FileText,    src: '/sounds/things/paper.mp3' },
      { id: 'clock',             label: '时钟',   icon: Clock,       src: '/sounds/things/clock.mp3' },
      { id: 'wind-chimes',       label: '风铃',   icon: Bell,        src: '/sounds/things/wind-chimes.mp3' },
      { id: 'singing-bowl',      label: '颂钵',   icon: Music,       src: '/sounds/things/singing-bowl.mp3' },
      { id: 'ceiling-fan',       label: '吊扇',   icon: Fan,         src: '/sounds/things/ceiling-fan.mp3' },
      { id: 'dryer',             label: '烘干机', icon: Wand,        src: '/sounds/things/dryer.mp3' },
      { id: 'slide-projector',   label: '幻灯机', icon: Projector,   src: '/sounds/things/slide-projector.mp3' },
      { id: 'boiling-water',     label: '沸水',   icon: FlaskRound,  src: '/sounds/things/boiling-water.mp3' },
      { id: 'bubbles',           label: '泡泡',   icon: Sparkles,    src: '/sounds/things/bubbles.mp3' },
      { id: 'tuning-radio',      label: '调台',   icon: Radio,       src: '/sounds/things/tuning-radio.mp3' },
      { id: 'morse-code',        label: '摩斯码', icon: Disc,        src: '/sounds/things/morse-code.mp3' },
      { id: 'washing-machine',   label: '洗衣机', icon: Wand,        src: '/sounds/things/washing-machine.mp3' },
      { id: 'vinyl-effect',      label: '黑胶',   icon: Disc,        src: '/sounds/things/vinyl-effect.mp3' },
      { id: 'windshield-wipers', label: '雨刷',   icon: Wrench,      src: '/sounds/things/windshield-wipers.mp3' },
    ],
  },
  {
    id: 'noise',
    label: '噪音',
    sounds: [
      { id: 'white-noise', label: '白噪音', icon: Music2,  src: '/sounds/noise/white-noise.wav' },
      { id: 'pink-noise',  label: '粉噪音', icon: Music3,  src: '/sounds/noise/pink-noise.wav' },
      { id: 'brown-noise', label: '棕噪音', icon: Music4,  src: '/sounds/noise/brown-noise.wav' },
    ],
  },
];

// 扁平索引：id -> sound（含 src/icon/label）
export const SOUND_BY_ID = (() => {
  const map = new Map();
  for (const cat of SOUND_CATEGORIES) {
    for (const s of cat.sounds) {
      map.set(s.id, { ...s, category: cat.id });
    }
  }
  return map;
})();

export const TOTAL_SOUNDS = SOUND_BY_ID.size;
