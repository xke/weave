type LiteralOperation = {
  literal_:
    | string
    | number
    | boolean
    | {[key: string]: LiteralOperation}
    | LiteralOperation[];
};

type GetFieldOperator = {
  get_field_: string;
};

type ConvertSpec = {
  input: Operand;
  to: 'double' | 'string' | 'int' | 'bool';
};

type ConvertOperation = {
  convert_: ConvertSpec;
};

type AndOperation = {
  and_: Operand[];
};

type OrOperation = {
  or_: Operand[];
};

type NotOperation = {
  not_: [Operand];
};

type EqOperation = {
  eq_: [Operand, Operand];
};

type GtOperation = {
  gt_: [Operand, Operand];
};

type GteOperation = {
  gte_: [Operand, Operand];
};

type SubstrOperation = {
  substr_: [Operand, Operand];
};

type Operation =
  | AndOperation
  | OrOperation
  | NotOperation
  | EqOperation
  | GtOperation
  | GteOperation
  | SubstrOperation;

type Operand =
  | LiteralOperation
  | GetFieldOperator
  | ConvertOperation
  | Operation;

export type Query = {
  expr_: Operation;
};