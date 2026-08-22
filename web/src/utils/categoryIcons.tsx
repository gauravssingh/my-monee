/**
 * Returns a semantic icon for a category based on its name and expense type.
 */
export function getCategoryIcon(name: string, expenseType?: string): string {
  const n = (name || "").toLowerCase().trim();

  // Food & Dining
  if (
    n.includes("food") ||
    n.includes("dining") ||
    n.includes("restaurant") ||
    n.includes("grocery") ||
    n.includes("groceries") ||
    n.includes("cafe") ||
    n.includes("coffee") ||
    n.includes("tea") ||
    n.includes("swiggy") ||
    n.includes("zomato") ||
    n.includes("zepto") ||
    n.includes("blinkit") ||
    n.includes("instamart") ||
    n.includes("supermarket") ||
    n.includes("snack") ||
    n.includes("bakery") ||
    n.includes("sweet")
  ) {
    return "🍔";
  }

  // Shopping & Retail
  if (
    n.includes("shop") ||
    n.includes("amazon") ||
    n.includes("flipkart") ||
    n.includes("clothing") ||
    n.includes("apparel") ||
    n.includes("fashion") ||
    n.includes("retail") ||
    n.includes("electronics") ||
    n.includes("gadget") ||
    n.includes("myntra")
  ) {
    return "🛍️";
  }

  // Travel & Transport
  if (
    n.includes("travel") ||
    n.includes("flight") ||
    n.includes("airline") ||
    n.includes("hotel") ||
    n.includes("trip") ||
    n.includes("vacation") ||
    n.includes("uber") ||
    n.includes("ola") ||
    n.includes("cab") ||
    n.includes("taxi") ||
    n.includes("train") ||
    n.includes("irctc") ||
    n.includes("metro") ||
    n.includes("bus")
  ) {
    return "✈️";
  }

  // Fuel & Gas
  if (
    n.includes("fuel") ||
    n.includes("petrol") ||
    n.includes("diesel") ||
    n.includes("gas station") ||
    n.includes("cng")
  ) {
    return "⛽";
  }

  // Entertainment & Media
  if (
    n.includes("entertain") ||
    n.includes("movie") ||
    n.includes("cinema") ||
    n.includes("netflix") ||
    n.includes("prime") ||
    n.includes("spotify") ||
    n.includes("youtube") ||
    n.includes("gaming") ||
    n.includes("game") ||
    n.includes("subscription") ||
    n.includes("theatre") ||
    n.includes("music") ||
    n.includes("bookmyshow")
  ) {
    return "🎬";
  }

  // Utilities & Bills
  if (
    n.includes("utilit") ||
    n.includes("bill") ||
    n.includes("electric") ||
    n.includes("water") ||
    n.includes("power") ||
    n.includes("internet") ||
    n.includes("wifi") ||
    n.includes("broadband") ||
    n.includes("mobile") ||
    n.includes("recharge") ||
    n.includes("dth")
  ) {
    return "💡";
  }

  // Home & Living
  if (
    n.includes("home") ||
    n.includes("rent") ||
    n.includes("housing") ||
    n.includes("maintenance") ||
    n.includes("society") ||
    n.includes("furniture") ||
    n.includes("decor") ||
    n.includes("repair") ||
    n.includes("maid") ||
    n.includes("cook")
  ) {
    return "🏠";
  }

  // Education & Learning
  if (
    n.includes("educat") ||
    n.includes("school") ||
    n.includes("college") ||
    n.includes("tuition") ||
    n.includes("course") ||
    n.includes("book") ||
    n.includes("udemy") ||
    n.includes("coursera") ||
    n.includes("learning") ||
    n.includes("training")
  ) {
    return "🎓";
  }

  // Vehicle & Automobile
  if (
    n.includes("car") ||
    n.includes("auto") ||
    n.includes("vehicle") ||
    n.includes("bike") ||
    n.includes("service") ||
    n.includes("toll") ||
    n.includes("fastag") ||
    n.includes("parking")
  ) {
    return "🚗";
  }

  // Financial, Loans, EMI, Fees & Interest
  if (
    n.includes("financial") ||
    n.includes("loan") ||
    n.includes("emi") ||
    n.includes("fee") ||
    n.includes("interest") ||
    n.includes("charge") ||
    n.includes("bank") ||
    n.includes("card") ||
    n.includes("insurance") ||
    n.includes("tax") ||
    n.includes("penalty") ||
    expenseType === "financial"
  ) {
    return "💳";
  }

  // Investments
  if (
    n.includes("invest") ||
    n.includes("stock") ||
    n.includes("mutual") ||
    n.includes("mf") ||
    n.includes("zerodha") ||
    n.includes("groww") ||
    n.includes("sip") ||
    n.includes("gold") ||
    n.includes("crypto") ||
    n.includes("deposit") ||
    n.includes("fd") ||
    expenseType === "investment"
  ) {
    return "📈";
  }

  // Transfers
  if (
    n.includes("transfer") ||
    n.includes("self") ||
    n.includes("movement") ||
    expenseType === "transfer"
  ) {
    return "↔️";
  }

  // Healthcare & Medical
  if (
    n.includes("health") ||
    n.includes("medic") ||
    n.includes("pharmacy") ||
    n.includes("hospital") ||
    n.includes("doctor") ||
    n.includes("clinic") ||
    n.includes("test") ||
    n.includes("lab") ||
    n.includes("apollo") ||
    n.includes("1mg")
  ) {
    return "🏥";
  }

  // Personal Care & Fitness
  if (
    n.includes("personal") ||
    n.includes("salon") ||
    n.includes("spa") ||
    n.includes("grooming") ||
    n.includes("gym") ||
    n.includes("fitness") ||
    n.includes("cult") ||
    n.includes("yoga")
  ) {
    return "✂️";
  }

  // Salary & Income
  if (
    n.includes("salary") ||
    n.includes("income") ||
    n.includes("bonus") ||
    n.includes("dividend") ||
    n.includes("freelance") ||
    n.includes("interest received")
  ) {
    return "💰";
  }

  // Fallback by expense type
  if (expenseType === "essential") return "💡";
  if (expenseType === "discretionary") return "🛍️";

  return "🏷️";
}
