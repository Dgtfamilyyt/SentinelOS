export const ElementData = {
  _elements: [
    { atomic_number: 1, symbol: "H", name: "Hydrogen", atomic_mass: 1.008, common_valences: [1], category: "nonmetal", color: 0xffffff },
    { atomic_number: 6, symbol: "C", name: "Carbon", atomic_mass: 12.011, common_valences: [4], category: "nonmetal", color: 0x222222 },
    { atomic_number: 7, symbol: "N", name: "Nitrogen", atomic_mass: 14.007, common_valences: [3,5], category: "nonmetal", color: 0x0000ff },
    { atomic_number: 8, symbol: "O", name: "Oxygen", atomic_mass: 15.999, common_valences: [2], category: "nonmetal", color: 0xff0000 },
    { atomic_number: 9, symbol: "F", name: "Fluorine", atomic_mass: 18.998, common_valences: [1], category: "halogen", color: 0x00ffff }
    // Add more elements as needed
  ],
  getElements() { return this._elements; }
};
