/** Maps synthesis `category` codes (Italian legacy + English) to display labels. */
const CATEGORY_LABELS: Record<string, string> = {
  esame_laboratorio: "Lab test",
  patologia_remota: "Past condition",
  farmaco: "Medication",
  diagnosi: "Diagnosis",
  parametro_vitale: "Vital sign",
  lab_test: "Lab test",
  past_condition: "Past condition",
  medication: "Medication",
  diagnosis: "Diagnosis",
  vital_sign: "Vital sign",
};

export function formatClinicalEntityCategory(category: string): string {
  const key = category.trim().toLowerCase();
  return CATEGORY_LABELS[key] ?? category.replace(/_/g, " ");
}
