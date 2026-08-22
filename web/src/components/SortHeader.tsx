type Props = {
  label: string;
  active: boolean;
  dir: "asc" | "desc";
  onClick: () => void;
  className?: string;
  style?: React.CSSProperties;
};

export default function SortHeader({ label, active, dir, onClick, className, style }: Props) {
  return (
    <th className={className} style={style} aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className="th-sort" onClick={onClick}>
        {label}
        <span className="th-sort-arrow" aria-hidden="true">
          {active ? (dir === "asc" ? "▲" : "▼") : ""}
        </span>
      </button>
    </th>
  );
}
